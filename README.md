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

## Step B4 — Execute 

```bash
cd /home/regis/JIS-2026-main/outside-proof-of-concept/sources

./integration_process
```

# Part C — Statistical analysis

The repository contains the analysis script used to compare the trusted and conventional configurations:

```text
evaluation/script.py
```

The campaign files are read directly from:

```text
inside-proof-of-concept/metrics/all_metrics.csv
outside-proof-of-concept/metrics/all_metrics.csv
```

## Step C1 — Run the analysis script

```bash
cd /home/regis/JIS-2026-main
python3 evaluation/script.py
```

The script produces:

- console output; and
- `evaluation/analysis_results.log`.

## Step C2 — What the script computes

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
