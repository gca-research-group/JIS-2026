from __future__ import annotations
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import threading
from types import SimpleNamespace
import time
import urllib.request
import urllib.parse
import uuid
from pathlib import Path

try:
    from flask import Flask, request, jsonify
except Exception:  # pragma: no cover
    Flask = None
    request = None
    jsonify = None

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.metrics import append_metric, default_metrics_file

SOURCE_FOLDER = str(Path(__file__).resolve().parent / 'programs-data-base' / 'sources')
EXECUTABLE_FOLDER = str(Path(__file__).resolve().parent / 'programs-data-base' / 'cheri-caps-executables')
CERTIFICATE_FOLDER = str(Path(__file__).resolve().parent / 'programs-data-base' / 'certificates')
FILE_DATABASE = str(Path(__file__).resolve().parent / 'programs-data-base' / 'file_database.json')
ALLOWED_EXTENSIONS = {'c'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024
METRICS_FILE = os.environ.get('METRICS_FILE', str(default_metrics_file(__file__)))

# Fallback certificate bundled with the repository, used when a newly compiled
# executable has no certificate pair yet.
FALLBACK_CERT_DIR = Path(CERTIFICATE_FOLDER) / 'integration_process_1719651695'

SERVICE_URLS = {
    # Defaults match the reproducible local deployment described in README.md.
    # They can be overridden without editing the code when services run remotely.
    'health-registry-service': os.environ.get('HEALTH_REGISTRY_SERVICE_URL', 'https://127.0.0.1:8100/api/request'),
    'hospital-service': os.environ.get('HOSPITAL_SERVICE_URL', 'https://127.0.0.1:8101/api/post'),
    'messaging-service': os.environ.get('MESSAGING_SERVICE_URL', 'https://127.0.0.1:9100/api/post'),
}

app = Flask(__name__) if Flask else None
if app:
    app.config.update(
        SOURCE_FOLDER=SOURCE_FOLDER,
        EXECUTABLE_FOLDER=EXECUTABLE_FOLDER,
        CERTIFICATE_FOLDER=CERTIFICATE_FOLDER,
        MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH
    )

file_db: dict[int, dict] = {}


def now_ms() -> float:
    return time.perf_counter() * 1000.0




def run_shell_command(command: str, env: dict | None = None) -> SimpleNamespace:
    """Run a shell command without relying on subprocess in request threads.

    Some CheriBSD/Python builds may raise ``signal only works in main thread``
    when a subprocess is created from a Flask worker thread. The launcher must
    execute integration processes from an HTTP request while still serving the
    callbacks issued by the process. This helper uses fork/exec on POSIX systems
    and captures stdout/stderr through pipes, avoiding Python-level signal
    registration in worker threads.
    """
    if not hasattr(os, 'fork'):
        completed = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        return SimpleNamespace(
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode
        )

    stdout_r, stdout_w = os.pipe()
    stderr_r, stderr_w = os.pipe()
    pid = os.fork()

    if pid == 0:
        try:
            os.close(stdout_r)
            os.close(stderr_r)
            os.dup2(stdout_w, 1)
            os.dup2(stderr_w, 2)
            os.close(stdout_w)
            os.close(stderr_w)
            if env is None:
                os.execv('/bin/sh', ['/bin/sh', '-c', command])
            else:
                os.execve('/bin/sh', ['/bin/sh', '-c', command], env)
        except BaseException as exc:  # pragma: no cover - child process path
            try:
                os.write(2, str(exc).encode('utf-8', errors='replace'))
            finally:
                os._exit(127)

    os.close(stdout_w)
    os.close(stderr_w)

    import select
    output = {stdout_r: bytearray(), stderr_r: bytearray()}
    open_fds = {stdout_r, stderr_r}

    while open_fds:
        readable, _, _ = select.select(list(open_fds), [], [])
        for fd in readable:
            chunk = os.read(fd, 8192)
            if chunk:
                output[fd].extend(chunk)
            else:
                open_fds.remove(fd)
                os.close(fd)

    _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        returncode = os.WEXITSTATUS(status)
    elif os.WIFSIGNALED(status):
        returncode = -os.WTERMSIG(status)
    else:
        returncode = status

    return SimpleNamespace(
        stdout=bytes(output[stdout_r]),
        stderr=bytes(output[stderr_r]),
        returncode=returncode
    )


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def load_file_database() -> None:
    global file_db
    p = Path(FILE_DATABASE)
    if not p.exists():
        file_db = {}
        return

    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        file_db = {}
        save_file_database()
        return

    base = Path(FILE_DATABASE).parent.parent
    file_db = {}

    for k, v in raw.items():
        entry = dict(v)

        for field in ('file_path',):
            if field in entry:
                pp = Path(entry[field])
                resolved = pp if pp.is_absolute() else (base / pp).resolve()
                if not resolved.exists():
                    local_candidate = Path(SOURCE_FOLDER) / resolved.name
                    if local_candidate.exists():
                        resolved = local_candidate.resolve()
                entry[field] = str(resolved)

        for field in ('executables', 'certificates'):
            if field in entry:
                repaired = []
                for x in entry[field]:
                    xp = Path(x)
                    resolved = xp if xp.is_absolute() else (base / xp).resolve()
                    if not resolved.exists():
                        folder = Path(EXECUTABLE_FOLDER) if field == 'executables' else Path(CERTIFICATE_FOLDER)
                        local_candidate = folder / resolved.name
                        if local_candidate.exists():
                            resolved = local_candidate.resolve()
                    repaired.append(str(resolved))
                entry[field] = repaired

        file_db[int(k)] = entry


def save_file_database() -> None:
    Path(FILE_DATABASE).parent.mkdir(parents=True, exist_ok=True)
    Path(FILE_DATABASE).write_text(
        json.dumps({str(k): v for k, v in file_db.items()}, indent=2),
        encoding='utf-8'
    )


def handle_exit_signal(signum, frame):
    save_file_database()
    sys.exit(0)


def _metric(
    operation: str,
    metric: str,
    value_ms: float,
    run_id: str = '',
    program_id: str = '',
    service_id: str = ''
) -> None:
    append_metric(
        __file__,
        'launcher',
        operation,
        metric,
        value_ms,
        run_id=run_id,
        program_id=program_id,
        service_id=service_id,
        metrics_file=METRICS_FILE
    )


class Launcher:
    def __init__(self):
        self.services_url = SERVICE_URLS

    def retrieveProgram(self, program_id: int, run_id: str = '') -> str:
        t0 = now_ms()
        if program_id not in file_db:
            raise FileNotFoundError('Invalid program selected')

        path = file_db[program_id]['file_path']
        if not os.path.exists(path):
            raise FileNotFoundError('Source file does not exist')

        _metric('start', 'retrieveProgram_ms', now_ms() - t0, run_id, str(program_id))
        return path

    def createCompartment(self, program_id: int, run_id: str = '') -> str:
        t0 = now_ms()
        compartment_id = f'compartment-{program_id}'
        _metric('start', 'createCompartment_ms', now_ms() - t0, run_id, str(program_id))
        return compartment_id

    def deploy(self, program_id: int, executable_path: str, run_id: str = '') -> str:
        t0 = now_ms()
        _metric('start', 'deploy_ms', now_ms() - t0, run_id, str(program_id))
        return executable_path

    def compile(self, program_id: int, run_id: str = '') -> dict:
        t0 = now_ms()
        src = self.retrieveProgram(program_id, run_id)

        timestamp = int(time.time() * 1000)
        executable_name = f"{Path(src).stem}_{timestamp}"
        executable_path = os.path.join(EXECUTABLE_FOLDER, executable_name)
        os.makedirs(EXECUTABLE_FOLDER, exist_ok=True)

        compiler = os.environ.get('MORELLO_CC', 'clang-morello')
        compiler_flags = os.environ.get('MORELLO_CFLAGS', '-march=morello+c64 -mabi=purecap -g')
        linker_flags = os.environ.get('MORELLO_LDFLAGS', '-L. -lssl -lcrypto -lpthread')
        compile_command = (
            f"{compiler} {compiler_flags} "
            f"-o {executable_path} {src} {linker_flags}"
        )

        result = run_shell_command(compile_command)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode('utf-8', errors='replace') or result.stdout.decode('utf-8', errors='replace') or f'Compilation failed with return code {result.returncode}')

        cert_dir = os.path.join(CERTIFICATE_FOLDER, executable_name)
        os.makedirs(cert_dir, exist_ok=True)

        file_db[program_id].setdefault('executables', []).append(executable_path)
        file_db[program_id].setdefault('certificates', []).append(cert_dir)
        save_file_database()

        _metric('start', 'compile_ms', now_ms() - t0, run_id, str(program_id))
        return {
            'executable_path': executable_path,
            'certificate_path': cert_dir,
            'output': result.stdout.decode('utf-8', errors='replace'),
            'error_output': result.stderr.decode('utf-8', errors='replace')
        }

    def generateAttestableDoc(self, program_id: int, executable_path: str, run_id: str = '') -> dict:
        t0 = now_ms()
        exe_hash = ''

        if os.path.exists(executable_path):
            import hashlib
            exe_hash = hashlib.sha256(Path(executable_path).read_bytes()).hexdigest()

        doc = {
            'program_id': program_id,
            'executable_path': executable_path,
            'sha256': exe_hash
        }

        _metric('start', 'generateAttestableDoc_ms', now_ms() - t0, run_id, str(program_id))
        return doc

    def _get_cert_paths(self, cert_dir: str | Path) -> tuple[Path, Path]:
        cert_dir = Path(cert_dir)
        cert_path = cert_dir / 'certificate.pem'
        public_key_path = cert_dir / 'public_key.pem'
        return cert_path, public_key_path

    def _existing_certificate_available(self, cert_dir: str | Path) -> bool:
        cert_path, public_key_path = self._get_cert_paths(cert_dir)
        return cert_path.exists() and public_key_path.exists()

    def _find_reusable_certificate_pair(self, program_id: int) -> tuple[Path, Path] | None:
        """
        Ordem de busca:
        1) diretórios do file_db (mais recente -> mais antigo)
        2) diretório fallback manual
        """
        info = file_db.get(program_id, {})
        cert_dirs = info.get('certificates', [])

        for cert_dir in reversed(cert_dirs):
            cert_path, public_key_path = self._get_cert_paths(cert_dir)
            if cert_path.exists() and public_key_path.exists():
                return cert_path, public_key_path

        # Fallback manual explícito
        fallback_cert, fallback_pub = self._get_cert_paths(FALLBACK_CERT_DIR)
        if fallback_cert.exists() and fallback_pub.exists():
            return fallback_cert, fallback_pub

        return None

    def _copy_existing_certificate_pair(self, src_cert: Path, src_pub: Path, dst_dir: str | Path) -> dict:
        dst_dir_path = Path(dst_dir)
        dst_dir_path.mkdir(parents=True, exist_ok=True)

        dst_cert = dst_dir_path / 'certificate.pem'
        dst_pub = dst_dir_path / 'public_key.pem'

        shutil.copy2(src_cert, dst_cert)
        shutil.copy2(src_pub, dst_pub)

        return {
            'certificate_path': str(dst_cert),
            'public_key_path': str(dst_pub),
            'reused_existing': True
        }

    def generateCertificate(self, program_id: int, executable_path: str, cert_dir: str, run_id: str = '') -> dict:
        t0 = now_ms()

        # 1) Se o diretório atual já tem o par, reutiliza
        if self._existing_certificate_available(cert_dir):
            cert_path, public_key_path = self._get_cert_paths(cert_dir)
            result = {
                'certificate_path': str(cert_path),
                'public_key_path': str(public_key_path),
                'reused_existing': True
            }
            _metric('start', 'generateCertificate_ms', now_ms() - t0, run_id, str(program_id))
            return result

        # 2) Procura par reutilizável em diretórios anteriores ou no fallback manual
        reusable = self._find_reusable_certificate_pair(program_id)
        if reusable is not None:
            src_cert, src_pub = reusable
            result = self._copy_existing_certificate_pair(src_cert, src_pub, cert_dir)
            _metric('start', 'generateCertificate_ms', now_ms() - t0, run_id, str(program_id))
            return result

        # 3) Generate simulated attestation material in plain text.
        # The proof-of-concept keeps the certificate/public-key file names so the
        # same Launcher and DigitalService flow can run on CheriBSD without the
        # Python cryptography package.
        import hashlib
        digest = ''
        exe = Path(executable_path)
        if exe.exists():
            digest = hashlib.sha256(exe.read_bytes()).hexdigest()

        cert_dir_path = Path(cert_dir)
        cert_dir_path.mkdir(parents=True, exist_ok=True)
        cert_path = cert_dir_path / 'certificate.pem'
        public_key_path = cert_dir_path / 'public_key.pem'
        private_key_path = cert_dir_path / 'private_key.pem'

        payload = {
            'type': 'SIMULATED_ATTESTATION_CERTIFICATE',
            'program_id': program_id,
            'program': exe.name,
            'sha256': digest,
            'issued_at': int(time.time()),
            'note': 'plain-text attestation material for proof-of-concept execution'
        }
        cert_path.write_text('SIMULATED_ATTESTATION_CERTIFICATE\n' + json.dumps(payload, indent=2), encoding='utf-8')
        public_key_path.write_text('SIMULATED_PUBLIC_KEY\n' + digest, encoding='utf-8')
        private_key_path.write_text('SIMULATED_PRIVATE_KEY\n' + digest, encoding='utf-8')

        result = {
            'certificate_path': str(cert_path),
            'public_key_path': str(public_key_path),
            'private_key_path': str(private_key_path),
            'simulated': True
        }
        _metric('start', 'generateCertificate_ms', now_ms() - t0, run_id, str(program_id))
        return result

    def sign(self, program_id: int, run_id: str = '') -> None:
        t0 = now_ms()
        _metric('start', 'sign_ms', now_ms() - t0, run_id, str(program_id))

    def get_latest_executable(self, program_id: int) -> str:
        info = file_db[program_id]
        executables = info.get('executables', [])
        if not executables:
            raise FileNotFoundError('No executable registered for this program')

        exe = executables[-1]
        if not os.path.exists(exe):
            raise FileNotFoundError('Executable path does not exist')

        return exe

    def get_latest_certificate_dir(self, program_id: int) -> str:
        info = file_db[program_id]
        certificates = info.get('certificates', [])
        if not certificates:
            raise FileNotFoundError('No certificate directory registered for this program')

        cert_dir = certificates[-1]
        if not os.path.exists(cert_dir):
            raise FileNotFoundError('Certificate directory path does not exist')

        return cert_dir

    def getIntegratedServices(self, program_id: int, run_id: str = '') -> list[str]:
        t0 = now_ms()
        services = list(self.services_url.keys())
        _metric('start', 'getIntegratedServices_ms', now_ms() - t0, run_id, str(program_id))
        return services

    def exchangeKeys(self, program_id: int, services: list[str], run_id: str = '') -> dict:
        t0 = now_ms()
        service_public_keys = {srv_id: f'{srv_id}-public-key' for srv_id in services}
        _metric('start', 'exchangeKeys_ms', now_ms() - t0, run_id, str(program_id))
        return service_public_keys

    def lookupService(self, srv_id: str, run_id: str = '', program_id: str = '', operation: str = 'read_write') -> str:
        t0 = now_ms()
        if srv_id not in self.services_url:
            raise KeyError(f'Unknown service id: {srv_id}')

        url = self.services_url[srv_id]
        _metric(operation, 'lookupService_ms', now_ms() - t0, run_id, program_id, srv_id)
        return url

    def getCertificate(self, program_id: int, run_id: str = '', operation: str = 'read_write', service_id: str = '') -> str:
        t0 = now_ms()
        cert_path = Path(self.get_latest_certificate_dir(program_id)) / 'certificate.pem'
        if not cert_path.exists():
            raise FileNotFoundError(f'Certificate file not found: {cert_path}')

        pem = cert_path.read_text(encoding='utf-8')
        _metric(operation, 'getCertificate_ms', now_ms() - t0, run_id, str(program_id), service_id)
        return pem

    def getProgramPublicKey(self, program_id: int, run_id: str = '', operation: str = 'read', service_id: str = '') -> str:
        t0 = now_ms()
        public_key_path = Path(self.get_latest_certificate_dir(program_id)) / 'public_key.pem'
        if not public_key_path.exists():
            raise FileNotFoundError(f'Public key file not found: {public_key_path}')

        pem = public_key_path.read_text(encoding='utf-8')
        _metric(operation, 'getProgramPublicKey_ms', now_ms() - t0, run_id, str(program_id), service_id)
        return pem

    def _post_json(self, url: str, payload: dict) -> dict:
        import ssl
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            body = resp.read().decode('utf-8')
            return json.loads(body) if body else {}


    def _get_json(self, url: str) -> dict:
        import ssl
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(url, context=ctx, timeout=5) as resp:
            body = resp.read().decode('utf-8')
            return json.loads(body) if body else {}

    def validateServices(self, program_id: int, run_id: str = '') -> None:
        """Ensure that the three *inside* healthcare services are running before execution.

        The inside and outside proof-of-concept use the same TCP ports. Without
        this check it is easy to accidentally start the outside services while
        executing the trusted configuration, which mixes metrics between the
        two experiments.
        """
        t0 = now_ms()
        for srv_id, service_url in self.services_url.items():
            parsed = urllib.parse.urlsplit(service_url)
            health_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, '/api/health', '', ''))
            try:
                status = self._get_json(health_url)
            except Exception as exc:
                raise RuntimeError(f"Service '{srv_id}' is not reachable at {health_url}: {exc}") from exc

            if status.get('serviceId') != srv_id:
                raise RuntimeError(
                    f"Unexpected service at {health_url}: expected '{srv_id}', "
                    f"received '{status.get('serviceId')}'."
                )
            if status.get('environment') != 'inside':
                raise RuntimeError(
                    f"Service '{srv_id}' belongs to environment "
                    f"'{status.get('environment')}', not 'inside'. Start the services "
                    "from inside-proof-of-concept before running the trusted experiment."
                )
        _metric('experimental_control', 'validateServices_ms', now_ms() - t0, run_id, str(program_id))

    def start(self, program_id: int, force_compile: bool = False, run_id: str = '', patient_id: str = 'P001') -> dict:
        # A run identifier is created once by the Launcher and propagated to
        # the integration process and every digital service involved in it.
        if not run_id:
            run_id = f"inside-{program_id}-{uuid.uuid4().hex}"

        total_t0 = now_ms()
        self.retrieveProgram(program_id, run_id)

        compile_result = None
        executable_path = None
        cert_dir = None

        needs_compile = force_compile or not file_db[program_id].get('executables')
        if not needs_compile:
            try:
                candidate_executable = self.get_latest_executable(program_id)
                source_path = file_db[program_id]['file_path']
                needs_compile = os.path.getmtime(source_path) > os.path.getmtime(candidate_executable)
            except (FileNotFoundError, OSError):
                needs_compile = True

        # The repeated experimental campaign uses a precompiled executable so
        # compilation does not contaminate Launcher.start() or the 30 measured
        # runs. Compilation is allowed inside start() only when explicitly
        # requested through force_compile=True.
        if needs_compile and not force_compile:
            raise RuntimeError(
                'The Integration Process must be compiled before a measured execution. '
                'Run `python3 command-line-interface.py compile %d` first.' % program_id
            )

        if needs_compile:
            compile_result = self.compile(program_id, run_id)
            executable_path = compile_result['executable_path']
            cert_dir = compile_result['certificate_path']
        else:
            executable_path = self.get_latest_executable(program_id)
            cert_dir = self.get_latest_certificate_dir(program_id)

        self.createCompartment(program_id, run_id)
        self.deploy(program_id, executable_path, run_id)
        services = self.getIntegratedServices(program_id, run_id)
        self.exchangeKeys(program_id, services, run_id)
        self.generateAttestableDoc(program_id, executable_path, run_id)
        self.generateCertificate(program_id, executable_path, cert_dir, run_id)
        self.sign(program_id, run_id)

        os.chmod(executable_path, stat.S_IRWXU)

        env = os.environ.copy()
        env['PROGRAM_ID'] = str(program_id)
        env['RUN_ID'] = run_id
        env['LAUNCHER_URL'] = 'https://127.0.0.1:5000'
        env['LAUNCHER_HOST'] = os.environ.get('LAUNCHER_HOST', '127.0.0.1')
        env['LAUNCHER_PORT'] = os.environ.get('LAUNCHER_PORT', '5001')
        env['MAX_LOOPS'] = '1'
        env['METRICS_FILE'] = METRICS_FILE
        env['PATIENT_ID'] = patient_id

        runner = os.environ.get('PROGRAM_RUNNER', 'proccontrol -m cheric18n -s enable {exe}')
        cmd = runner.format(exe=executable_path)

        t0 = now_ms()
        result = run_shell_command(cmd, env=env)
        _metric('start', 'run_ms', now_ms() - t0, run_id, str(program_id))
        _metric('start', 'start_total_ms', now_ms() - total_t0, run_id, str(program_id))

        return {
            'run_id': run_id,
            'compile_result': compile_result,
            'executable_path': executable_path,
            'output': result.stdout.decode('utf-8', errors='replace'),
            'error_output': result.stderr.decode('utf-8', errors='replace'),
            'returncode': result.returncode
        }


launcher = Launcher()


def register_signal_handlers() -> None:
    # Flask request handlers run in worker threads; signal handlers are valid
    # only in the main interpreter thread. Keep registration local to the
    # direct launcher startup path.
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, handle_exit_signal)
        signal.signal(signal.SIGTERM, handle_exit_signal)


if app:
    @app.route('/upload', methods=['POST'])
    def upload_file():
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['file']
        if file.filename == '' or not (file and allowed_file(file.filename)):
            return jsonify({'error': 'Invalid file type'}), 400

        filename = os.path.basename(file.filename)
        secure_filename = os.path.join(SOURCE_FOLDER, filename)
        os.makedirs(SOURCE_FOLDER, exist_ok=True)
        file.save(secure_filename)

        program_id = max(file_db.keys(), default=0) + 1
        file_db[program_id] = {
            'file_name': filename,
            'file_path': secure_filename,
            'executables': [],
            'certificates': []
        }
        save_file_database()
        return jsonify({'message': 'File successfully uploaded', 'program_id': program_id}), 200

    @app.route('/files', methods=['GET'])
    def list_files():
        return jsonify([{'id': file_id, **file_info} for file_id, file_info in file_db.items()]), 200

    @app.route('/files/<int:program_id>', methods=['DELETE'])
    def delete_program(program_id):
        if program_id not in file_db:
            return jsonify({'error': 'Program not found'}), 404

        info = file_db.pop(program_id)
        # Remove generated executables and certificate directories, but keep
        # uploaded source code unless it is outside the canonical source folder.
        for exe in info.get('executables', []):
            try:
                Path(exe).unlink(missing_ok=True)
            except Exception:
                pass
        for cert_dir in info.get('certificates', []):
            try:
                shutil.rmtree(cert_dir, ignore_errors=True)
            except Exception:
                pass
        save_file_database()
        return jsonify({'message': 'Program deleted'}), 200

    @app.route('/compile/<int:program_id>', methods=['POST'])
    def compile_program(program_id):
        payload = request.get_json(silent=True) or {}
        run_id = payload.get('runId', '')
        try:
            return jsonify({'message': 'Compilation successful', **launcher.compile(program_id, run_id)}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/execute/<int:program_id>', methods=['POST'])
    def execute_program(program_id):
        payload = request.get_json(silent=True) or {}
        run_id = str(payload.get('runId', '')).strip()
        if not run_id:
            run_id = f"inside-{program_id}-{uuid.uuid4().hex}"
        try:
            patient_id = str(payload.get('patientId', 'P001')).strip() or 'P001'
            # This health/configuration check is an experimental control. It is
            # intentionally executed before Launcher.start() so its latency is
            # not included in the API operation's measured total.
            launcher.validateServices(program_id, run_id)
            result = launcher.start(program_id, force_compile=payload.get('forceCompile', False), run_id=run_id, patient_id=patient_id)
            if result.get('returncode') != 0:
                return jsonify({
                    'error': 'Integration flow failed; this run must not be used as a successful sample.',
                    **result
                }), 500
            return jsonify({'message': 'Execution finished', **result}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    for p in [SOURCE_FOLDER, EXECUTABLE_FOLDER, CERTIFICATE_FOLDER, Path(FILE_DATABASE).parent]:
        Path(p).mkdir(parents=True, exist_ok=True)

    load_file_database()

    if not app:
        raise RuntimeError('Flask is required to run the launcher HTTP server.')

    register_signal_handlers()

    app.run(
        debug=False,
        ssl_context=('keys/cert.pem', 'keys/prk.pem'),
        host='127.0.0.1',
        port=5000,
        use_reloader=False,
        threaded=True
    )
