# Healthcare Integration Proof of Concept on ARM Morello

This repository contains two configurations of the same healthcare integration workflow:

1. The Hospital Service requests patient `P001` (or another `PATIENT_ID`).
2. `Read_act` retrieves the patient record from the Health Registry Service.
3. `Write_act` updates the Hospital Service.
4. A second `Write_act` records a notification in the Messaging Service.

The trusted configuration executes the Integration Process with CHERI compartmentalisation enabled through `proccontrol`. The conventional configuration executes the same business workflow directly, without the Launcher and without the compartment execution command. In both configurations, the three Digital Services are conventional Python/Flask processes and are co-located on the Morello Board for the experiment.

## Important implementation scope

The project measures the execution structure of the proof of concept. The certificate-verification and payload encryption/decryption functions are lightweight functional stubs that preserve the API-level control flow; they are not benchmarks of production cryptographic primitives. Likewise, `createCompartment()` and `deploy()` are prototype API operations. The protected execution of the Integration Process is activated by:

```text
proccontrol -m cheric18n -s enable <executable>
```

The service-environment check performed before each trusted execution is an experimental-control operation. Its latency is recorded as `validateServices_ms`, but it is deliberately outside the measured `Launcher.start()` interval.

## Canonical path

The commands below assume that the project is installed at:

```text
/home/regis/JIS-2026-main/
```

## Dependencies

Required system tools include `python3`, `pip`, `clang-morello`, `openssl`, and `proccontrol`. Python packages are listed in `requirements.txt`.

```sh
cd /home/regis/JIS-2026-main
python3 -m pip install -r requirements.txt
```

Before collecting a campaign, record the execution environment:

```sh
python3 evaluation/collect_system_info.py
```

## Preserved previous campaign

The measurements that were bundled with the original project are preserved unchanged under:

```text
reference-results/20260819-original-campaign/
```

The active `all_metrics.csv` files are reset in this adjusted package so a new campaign can be collected without mixing old and new samples.

# A. Trusted configuration

The trusted and conventional services use the same local ports. Do not run both configurations at the same time.

## A1. Stop processes left from an earlier execution

```sh
pkill -f API1.py || true
pkill -f API2.py || true
pkill -f API3.py || true
pkill -f launcher.py || true
```

## A2. Start the trusted Digital Services

Terminal 1:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/app-health-registry/api
python3 API1.py
```

Terminal 2:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/app-hospital/api
python3 API2.py
```

Terminal 3:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/app-messaging/api
python3 API3.py
```

Check the three endpoints:

```sh
curl -k https://127.0.0.1:8100/api/health
curl -k https://127.0.0.1:8101/api/health
curl -k https://127.0.0.1:9100/api/health
```

The responses must identify `health-registry-service`, `hospital-service`, and `messaging-service` with `environment: inside`.

## A3. Start the Launcher

Terminal 4:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher
python3 launcher.py
```

## A4. Compile the Integration Process once, before the measured campaign

Terminal 5:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher
python3 command-line-interface.py compile 2
```

Compilation is intentionally performed before the repeated campaign. A measured trusted run is rejected if it contains `compile_ms` under its campaign `run_id`.

## A5. Reset the active trusted campaign after compilation

```sh
cd /home/regis/JIS-2026-main
python3 evaluation/prepare_campaign.py trusted
```

This archives any active measurements, resets the trusted metrics CSV, and restores the Hospital and Messaging service data to the same initial state used by the conventional campaign. The compiled executable and its registration are preserved.

## A6. Run one validation execution

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher
python3 command-line-interface.py execute 2 --patient-id P001
```

Validate it:

```sh
cd /home/regis/JIS-2026-main
python3 evaluation/validate_metrics.py inside-proof-of-concept/metrics/all_metrics.csv --expected-runs 1
```

If it passes, reset the trusted campaign again before collecting the final 30 samples:

```sh
python3 evaluation/prepare_campaign.py trusted
```

## A7. Collect the final 30 trusted runs

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher
python3 command-line-interface.py campaign 2 --runs 30 --patient-id P001
```

Validate immediately:

```sh
cd /home/regis/JIS-2026-main
python3 evaluation/validate_metrics.py inside-proof-of-concept/metrics/all_metrics.csv --expected-runs 30
```

A valid trusted run contains exactly one `Read_act`, one Hospital `Write_act`, one Messaging `Write_act`, one `Execution`, all operation-level metrics used by the analysis, one `Launcher.start()` interval, and one service-environment validation interval outside `Launcher.start()`. No measured run may contain `compile_ms` or `execute_failed_ms`.

# B. Conventional configuration

Stop the trusted processes before starting the conventional services:

```sh
pkill -f API1.py || true
pkill -f API2.py || true
pkill -f API3.py || true
pkill -f launcher.py || true
```

## B1. Start the conventional Digital Services

Terminal 1:

```sh
cd /home/regis/JIS-2026-main/outside-proof-of-concept/app-health-registry/api
python3 API1.py
```

Terminal 2:

```sh
cd /home/regis/JIS-2026-main/outside-proof-of-concept/app-hospital/api
python3 API2.py
```

Terminal 3:

```sh
cd /home/regis/JIS-2026-main/outside-proof-of-concept/app-messaging/api
python3 API3.py
```

Check:

```sh
curl -k https://127.0.0.1:8100/api/health
curl -k https://127.0.0.1:8101/api/health
curl -k https://127.0.0.1:9100/api/health
```

The responses must report `environment: outside`.

## B2. Compile the conventional Integration Process

The conventional baseline preserves the compiler invocation used by the existing project: `clang-morello` without the purecap ABI override used by the trusted build.

```sh
cd /home/regis/JIS-2026-main/outside-proof-of-concept/sources
clang-morello -o integration_process integration_process.c -lssl -lcrypto
```

## B3. Prepare and validate one conventional run

```sh
cd /home/regis/JIS-2026-main
python3 evaluation/prepare_campaign.py conventional

METRICS_FILE=/home/regis/JIS-2026-main/outside-proof-of-concept/metrics/all_metrics.csv \
PROGRAM_ID=2 PATIENT_ID=P001 \
/home/regis/JIS-2026-main/outside-proof-of-concept/sources/integration_process

python3 evaluation/validate_metrics.py outside-proof-of-concept/metrics/all_metrics.csv --expected-runs 1
```

Reset again before the final campaign:

```sh
python3 evaluation/prepare_campaign.py conventional
```

## B4. Collect the final 30 conventional runs

```sh
cd /home/regis/JIS-2026-main
python3 evaluation/run_outside_campaign.py --runs 30 --patient-id P001 --program-id 2
```

Validate immediately:

```sh
python3 evaluation/validate_metrics.py outside-proof-of-concept/metrics/all_metrics.csv --expected-runs 30
```

# C. Statistical analysis

Only run the analysis after both validators report exactly 30 complete successful runs and zero incomplete/failed runs.

```sh
cd /home/regis/JIS-2026-main
python3 evaluation/script.py
```

The analysis is written to:

```text
evaluation/analysis_results.log
```

The script reports:

- mean and sample standard deviation for `Read_act`, both `Write_act` actions, and `Execution`;
- relative trusted-environment overhead;
- Shapiro--Wilk tests;
- two-sided Mann--Whitney U tests;
- Holm-adjusted p-values over the four cross-environment comparisons;
- Cliff's delta;
- IQR-based sensitivity analysis;
- operation-level trusted measurements for `Read_act` and both `Write_act` actions;
- `DigitalService.request()` and `DigitalService.post()` service-side totals separately from the enclosing Launcher request/post intervals;
- selected intervals within `Launcher.start()`;
- the service-environment validation interval as an experimental control outside `Launcher.start()`.

# D. Active output files

```text
inside-proof-of-concept/metrics/all_metrics.csv
outside-proof-of-concept/metrics/all_metrics.csv
evaluation/analysis_results.log
evaluation/system_info.txt
```
