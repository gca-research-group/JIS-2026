# iDevS — JIS 2026 FUMSSAR proof of concept

This project implements a healthcare scenario:

1. The Hospital Service requests patient `P001` (or another `PATIENT_ID`) as the business-flow input.
2. `Read_act` retrieves that patient from the Health Registry Service.
3. `Write_act` updates the Hospital Service record.
4. A second `Write_act` sends the availability notification to the Messaging Service.

## Inside (CHERI compartment)

Run each service in a separate terminal:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/app-health-registry/api
python3 API1.py
```

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/app-hospital/api
python3 API2.py
```

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/app-messaging/api
python3 API3.py
```

Start the Launcher:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher
python3 launcher.py
```

Use the CLI in another terminal:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher
python3 command-line-interface.py
```

The registered Integration Process is `program_id=2`. The interactive menu uses patient `P001`. The Click command also supports an explicit patient:

```sh
python3 command-line-interface.py execute 2 --patient-id P001
```

## Outside (conventional baseline)

Start the three services from `outside-proof-of-concept` on the same ports, after stopping the inside services. Compile and execute:

```sh
cd /home/regis/JIS-2026-main/outside-proof-of-concept/sources
clang-morello -o integration_process integration_process.c -lssl -lcrypto

METRICS_FILE=/home/regis/JIS-2026-main/outside-proof-of-concept/metrics/all_metrics.csv \
PROGRAM_ID=2 PATIENT_ID=P001 ./integration_process
```

## Metrics

The previously collected 30-run datasets are preserved exactly in:

```text
inside-proof-of-concept/metrics/all_metrics.csv
outside-proof-of-concept/metrics/all_metrics.csv
```

Validate a campaign:

```sh
cd /home/regis/JIS-2026-main
python3 evaluation/validate_metrics.py inside-proof-of-concept/metrics/all_metrics.csv --expected-runs 30
python3 evaluation/validate_metrics.py outside-proof-of-concept/metrics/all_metrics.csv --expected-runs 30
```

Run the statistical analysis:

```sh
python3 evaluation/script.py
```
