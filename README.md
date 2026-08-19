# Reproducing the proof-of-concept on the ARM Morello Board

This repository contains two reproducible configurations of the same healthcare integration proof of concept.

- **Trusted environment (`inside`)**: the Integration Process is executed through the Launcher inside a CHERI-based compartment on the ARM Morello Board.
- **Conventional environment (`outside`)**: the same Integration Process is executed outside CHERI-based compartments and communicates directly with the Digital Services, providing the conventional baseline.

The proof of concept implements an inter-organisational healthcare scenario involving primary healthcare services and a hospital managed by a different organisation. The workflow integrates three Digital Services:

- **Health Registry Service**: maintains patient data recorded by primary healthcare units (UBSs).
- **Hospital Service**: maintains the patient record used by the hospital.
- **Messaging Service**: records the notification sent to hospital staff after the patient record has been updated.

The business workflow receives a patient identifier as input (default: `P001`) and executes exactly one `Read_act` followed by two `Write_act` operations.

This README explains how to execute both configurations, validate the 30-run experimental campaigns, and reproduce the statistical analysis.

---

## What is executed in each environment

### 1. Trusted environment (`inside-proof-of-concept`)

The trusted configuration uses the Launcher as the mediator between the Integration Process and the three Digital Services.

The Launcher:

- retrieves the registered Integration Process source code;
- compiles it with `clang-morello` using the Morello pure-capability ABI;
- performs the prototype deployment and certificate-generation steps;
- checks that the Digital Services belong to the `inside` environment;
- propagates the `program_id`, `run_id`, and requested `patientId`;
- executes the Integration Process with:

```text
proccontrol -m cheric18n -s enable <executable>
```

- mediates `read()` and `write()` operations between the Integration Process and the Digital Services.

This configuration produces the metrics stored in:

```text
inside-proof-of-concept/metrics/all_metrics.csv
```

### 2. Conventional environment (`outside-proof-of-concept`)

The conventional configuration executes the same business workflow without the Launcher and without CHERI compartmentalisation. The Integration Process communicates directly with the same three types of Digital Services.

There is **no Launcher in the conventional configuration**. This configuration produces the baseline metrics stored in:

```text
outside-proof-of-concept/metrics/all_metrics.csv
```

---

## Hardware and software requirements

### Hardware

- ARM Morello Board (Research Morello SoC r0p0)
- 4 CPU cores
- 16 GB RAM

### Operating system

- CheriBSD

### Required tools

- `python3`
- `pip`
- `clang-morello`
- `openssl`
- `proccontrol`

### Python dependencies

Install the required Python packages:

```bash
python3 -m pip install flask flask-talisman cryptography requests click pandas numpy scipy
```

---

# Part A — Trusted environment (`inside-proof-of-concept`)

The trusted and conventional services use the same local ports. Do not run both configurations simultaneously.

Before starting the trusted environment, stop any Digital Services or Launcher left from a previous execution.

```bash
pkill -f API1.py || true
pkill -f API2.py || true
pkill -f API3.py || true
pkill -f launcher.py || true
```

## Step A1 — Start the Digital Services

Open three SSH terminals on the Morello Board.

### Terminal 1 — Health Registry Service

```bash
cd /home/regis/JIS-2026-main/inside-proof-of-concept/app-health-registry/api
python3 API1.py
```

Expected endpoints:

```text
https://127.0.0.1:8100/api/request
https://127.0.0.1:8100/api/health
```

### Terminal 2 — Hospital Service

```bash
cd /home/regis/JIS-2026-main/inside-proof-of-concept/app-hospital/api
python3 API2.py
```

Expected endpoints:

```text
https://127.0.0.1:8101/api/post
https://127.0.0.1:8101/api/health
```

### Terminal 3 — Messaging Service

```bash
cd /home/regis/JIS-2026-main/inside-proof-of-concept/app-messaging/api
python3 API3.py
```

Expected endpoints:

```text
https://127.0.0.1:9100/api/post
https://127.0.0.1:9100/api/health
```

## Step A2 — Verify the Digital Services

Before starting the Launcher, verify that the three services identify themselves as belonging to the trusted configuration:

```bash
curl -k https://127.0.0.1:8100/api/health
curl -k https://127.0.0.1:8101/api/health
curl -k https://127.0.0.1:9100/api/health
```

The responses must identify:

```text
health-registry-service  -> environment: inside
hospital-service         -> environment: inside
messaging-service        -> environment: inside
```

The Launcher also performs this verification before executing the Integration Process.

## Step A3 — Start the Launcher

Open a fourth terminal:

```bash
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher
python3 launcher.py
```

Expected endpoint:

```text
https://127.0.0.1:5000
```

## Step A4 — Start the CLI

Open a fifth terminal:

```bash
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher
python3 command-line-interface.py
```

The interactive menu provides:

```text
1. List files
2. Upload a file
3. Delete a program
4. Compile a program
5. Execute a program
6. Exit
```

The repository already contains the Integration Process registered as `program_id=2`, so a new upload is not required for a normal reproduction.

## Step A5 — List the registered source file

Choose option:

```text
1
```

Confirm that `program_id=2` refers to:

```text
/home/regis/JIS-2026-main/inside-proof-of-concept/launcher/programs-data-base/sources/integration_process.c
```

## Step A6 — Compile the Integration Process

Choose option:

```text
4
```

and enter:

```text
2
```

The Launcher compiles the source with the equivalent of:

```text
clang-morello -march=morello+c64 -mabi=purecap -g ... -lssl -lcrypto -lpthread
```

A newly generated executable is registered for `program_id=2`.

## Step A7 — Execute one validation run

Choose option:

```text
5
```

and enter:

```text
2
```

The interactive menu uses `patientId=P001` by default.

The same execution can be initiated explicitly from the command line:

```bash
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher
python3 command-line-interface.py execute 2 --patient-id P001
```

A successful execution must finish with HTTP status `200` and process return code `0`.

The complete business flow for a single `run_id` must contain:

```text
Read_act  -> Health Registry Service
Write_act -> Hospital Service
Write_act -> Messaging Service
Execution -> execute_total_ms
```

## Step A8 — Validate the test run

From the repository root:

```bash
cd /home/regis/JIS-2026-main
python3 evaluation/validate_metrics.py \
  inside-proof-of-concept/metrics/all_metrics.csv \
  --expected-runs 1
```

For a new campaign, the expected result after one clean validation run is:

```text
Complete successful runs: 1
Incomplete/failed runs: 0
Metric campaign is complete and internally consistent.
```

## Step A9 — Prepare a new 30-run campaign

The repository may already contain collected metrics. Preserve them before resetting the file if you intend to reproduce the experiment.

Example backup:

```bash
cd /home/regis/JIS-2026-main
cp inside-proof-of-concept/metrics/all_metrics.csv \
   inside-proof-of-concept/metrics/all_metrics.backup.csv
```

Reset the active CSV:

```bash
printf 'ts,run_id,component,operation,metric,value_ms,program_id,service_id\n' \
> inside-proof-of-concept/metrics/all_metrics.csv
```

## Step A10 — Execute 30 repetitions

Execute `program_id=2` thirty times, always using the same workload (`patientId=P001`).

The CLI command for one repetition is:

```bash
python3 /home/regis/JIS-2026-main/inside-proof-of-concept/launcher/command-line-interface.py \
  execute 2 --patient-id P001
```

After the campaign, the trusted CSV must contain 30 complete `run_id` values.

## Step A11 — Validate the trusted campaign

```bash
cd /home/regis/JIS-2026-main
python3 evaluation/validate_metrics.py \
  inside-proof-of-concept/metrics/all_metrics.csv \
  --expected-runs 30
```

Expected result:

```text
Complete successful runs: 30
Incomplete/failed runs: 0
Metric campaign is complete and internally consistent.
```

---

# Part B — Conventional environment (`outside-proof-of-concept`)

Stop all processes from the trusted configuration before starting the conventional configuration:

```bash
pkill -f API1.py || true
pkill -f API2.py || true
pkill -f API3.py || true
pkill -f launcher.py || true
```

The conventional environment does **not** use the Launcher.

## Step B1 — Start the Digital Services

Open three SSH terminals.

### Terminal 1 — Health Registry Service

```bash
cd /home/regis/JIS-2026-main/outside-proof-of-concept/app-health-registry/api
python3 API1.py
```

Expected endpoints:

```text
https://127.0.0.1:8100/api/request
https://127.0.0.1:8100/api/health
```

### Terminal 2 — Hospital Service

```bash
cd /home/regis/JIS-2026-main/outside-proof-of-concept/app-hospital/api
python3 API2.py
```

Expected endpoints:

```text
https://127.0.0.1:8101/api/post
https://127.0.0.1:8101/api/health
```

### Terminal 3 — Messaging Service

```bash
cd /home/regis/JIS-2026-main/outside-proof-of-concept/app-messaging/api
python3 API3.py
```

Expected endpoints:

```text
https://127.0.0.1:9100/api/post
https://127.0.0.1:9100/api/health
```

## Step B2 — Verify the Digital Services

```bash
curl -k https://127.0.0.1:8100/api/health
curl -k https://127.0.0.1:8101/api/health
curl -k https://127.0.0.1:9100/api/health
```

The responses must identify:

```text
health-registry-service  -> environment: outside
hospital-service         -> environment: outside
messaging-service        -> environment: outside
```

## Step B3 — Compile the Integration Process

Open a fourth terminal:

```bash
cd /home/regis/JIS-2026-main/outside-proof-of-concept/sources
clang-morello -o integration_process integration_process.c -lssl -lcrypto
```

The conventional executable is run directly, without `proccontrol -m cheric18n -s enable` and without the Launcher.

## Step B4 — Execute one validation run

```bash
cd /home/regis/JIS-2026-main/outside-proof-of-concept/sources

METRICS_FILE=/home/regis/JIS-2026-main/outside-proof-of-concept/metrics/all_metrics.csv \
PROGRAM_ID=2 \
PATIENT_ID=P001 \
./integration_process
```

Check the return code:

```bash
echo $?
```

Expected value:

```text
0
```

## Step B5 — Validate the test run

```bash
cd /home/regis/JIS-2026-main
python3 evaluation/validate_metrics.py \
  outside-proof-of-concept/metrics/all_metrics.csv \
  --expected-runs 1
```

For a new clean validation run, the expected result is:

```text
Complete successful runs: 1
Incomplete/failed runs: 0
Metric campaign is complete and internally consistent.
```

## Step B6 — Prepare a new 30-run campaign

Preserve an existing collected CSV before resetting it:

```bash
cd /home/regis/JIS-2026-main
cp outside-proof-of-concept/metrics/all_metrics.csv \
   outside-proof-of-concept/metrics/all_metrics.backup.csv
```

Reset the active CSV:

```bash
printf 'ts,run_id,component,operation,metric,value_ms,program_id,service_id\n' \
> outside-proof-of-concept/metrics/all_metrics.csv
```

## Step B7 — Execute 30 repetitions

```bash
cd /home/regis/JIS-2026-main/outside-proof-of-concept/sources

for i in $(seq 1 30); do
    echo "=== Execution $i/30 ==="

    METRICS_FILE=/home/regis/JIS-2026-main/outside-proof-of-concept/metrics/all_metrics.csv \
    PROGRAM_ID=2 \
    PATIENT_ID=P001 \
    ./integration_process

    if [ $? -ne 0 ]; then
        echo "Execution $i failed. Campaign stopped."
        exit 1
    fi
done
```

## Step B8 — Validate the conventional campaign

```bash
cd /home/regis/JIS-2026-main
python3 evaluation/validate_metrics.py \
  outside-proof-of-concept/metrics/all_metrics.csv \
  --expected-runs 30
```

Expected result:

```text
Complete successful runs: 30
Incomplete/failed runs: 0
Metric campaign is complete and internally consistent.
```

---

# Part C — Statistical analysis

The repository contains the analysis script used to compare the trusted and conventional configurations:

```text
evaluation/script.py
```

Unlike the earlier project organisation, it reads the canonical campaign files directly from:

```text
inside-proof-of-concept/metrics/all_metrics.csv
outside-proof-of-concept/metrics/all_metrics.csv
```

No manual copy to `evaluation/inside.csv` or `evaluation/outside.csv` is required.

## Step C1 — Validate both datasets

Before the statistical analysis, confirm that both campaigns contain exactly 30 complete runs:

```bash
cd /home/regis/JIS-2026-main

python3 evaluation/validate_metrics.py \
  inside-proof-of-concept/metrics/all_metrics.csv \
  --expected-runs 30

python3 evaluation/validate_metrics.py \
  outside-proof-of-concept/metrics/all_metrics.csv \
  --expected-runs 30
```

## Step C2 — Run the analysis script

```bash
cd /home/regis/JIS-2026-main
python3 evaluation/script.py
```

The script produces:

- console output; and
- `evaluation/analysis_results.log`.

## Step C3 — What the script computes

### Cross-environment comparison

The complete healthcare workflow is compared using:

- `read_act_total_ms` for the **Health Registry Service**;
- `write_act_total_ms` for the **Hospital Service**;
- `write_act_total_ms` for the **Messaging Service**;
- `execute_total_ms` for the complete Integration Process execution.

For each cross-environment metric, the script computes:

- number of valid samples;
- mean and standard deviation;
- relative overhead of the trusted configuration;
- Shapiro–Wilk normality tests;
- Mann–Whitney U test;
- Holm-adjusted p-values;
- Cliff's Delta;
- IQR-based robustness analysis.

### Trusted-environment internal analysis

The script also reports selected costs measured within:

- `Read_act`;
- `Write_act` to the Hospital Service;
- `Write_act` to the Messaging Service; and
- `Launcher.start()`.

Only complete and successful `run_id` values are included in the analysis.

---

# Expected output files

## Trusted environment

```text
inside-proof-of-concept/metrics/all_metrics.csv
```

## Conventional environment

```text
outside-proof-of-concept/metrics/all_metrics.csv
```

## Statistical analysis

```text
evaluation/analysis_results.log
```

---

# Main metrics collected by the proof-of-concept

## Cross-environment metrics

```text
read_act_total_ms
write_act_total_ms       # Hospital Service
write_act_total_ms       # Messaging Service
execute_total_ms
```

## Trusted `Read_act` metrics

```text
lookupService_ms
getCertificate_ms
getProgramPublicKey_ms
request_ms
launcher_read_total_ms
verifyCertificate_ms
retrieveLocalData_ms
encrypt_ms
decrypt_ms
read_act_total_ms
```

## Trusted `Write_act` metrics

For both the Hospital Service and Messaging Service:

```text
getServicePublicKey_ms
encrypt_ms
lookupService_ms
getCertificate_ms
post_ms
launcher_write_total_ms
verifyCertificate_ms
decrypt_ms
storeLocalData_ms
post_total_ms
write_act_total_ms
```

## `Launcher.start()` metrics

```text
retrieveProgram_ms
compile_ms
createCompartment_ms
deploy_ms
getIntegratedServices_ms
validateServices_ms
exchangeKeys_ms
generateAttestableDoc_ms
generateCertificate_ms
sign_ms
run_ms
start_total_ms
```

---

# Experimental consistency

A valid repetition must use one unique `run_id` and contain the complete business flow:

```text
1 x Read_act  -> health-registry-service
1 x Write_act -> hospital-service
1 x Write_act -> messaging-service
1 x Execution -> execute_total_ms
```

It must also contain the corresponding Digital Service request/post totals and must not contain `execute_failed_ms`.

Use `evaluation/validate_metrics.py` before performing any statistical analysis. This prevents incomplete executions from being mixed with successful runs.
