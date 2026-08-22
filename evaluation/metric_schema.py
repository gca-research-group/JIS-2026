from __future__ import annotations

# Metrics that define one complete business workflow in either environment.
CORE_FLOW = [
    ("integration_process", "read", "read_act_total_ms", "health-registry-service"),
    ("integration_process", "write", "write_act_total_ms", "hospital-service"),
    ("integration_process", "write", "write_act_total_ms", "messaging-service"),
    ("integration_process", "execute", "execute_total_ms", ""),
    ("digital_service", "request", "request_total_ms", "health-registry-service"),
    ("digital_service", "post", "post_total_ms", "hospital-service"),
    ("digital_service", "post", "post_total_ms", "messaging-service"),
]

# Additional metrics required for every valid trusted run because Section 7
# analyses these operation-level intervals. The validation step is recorded as
# experimental_control and is intentionally outside Launcher.start().
TRUSTED_INTERNAL = [
    ("launcher", "read", "lookupService_ms", "health-registry-service"),
    ("launcher", "read", "getCertificate_ms", "health-registry-service"),
    ("launcher", "read", "getProgramPublicKey_ms", "health-registry-service"),
    ("launcher", "read", "request_ms", "health-registry-service"),
    ("launcher", "read", "launcher_read_total_ms", "health-registry-service"),
    ("integration_process", "read", "decrypt_ms", "health-registry-service"),
    ("digital_service", "request", "verifyCertificate_ms", "health-registry-service"),
    ("digital_service", "request", "retrieveLocalData_ms", "health-registry-service"),
    ("digital_service", "request", "encrypt_ms", "health-registry-service"),

    ("integration_process", "write", "getServicePublicKey_ms", "hospital-service"),
    ("integration_process", "write", "encrypt_ms", "hospital-service"),
    ("launcher", "write", "lookupService_ms", "hospital-service"),
    ("launcher", "write", "getCertificate_ms", "hospital-service"),
    ("launcher", "write", "post_ms", "hospital-service"),
    ("launcher", "write", "launcher_write_total_ms", "hospital-service"),
    ("digital_service", "post", "verifyCertificate_ms", "hospital-service"),
    ("digital_service", "post", "decrypt_ms", "hospital-service"),
    ("digital_service", "post", "storeLocalData_ms", "hospital-service"),

    ("integration_process", "write", "getServicePublicKey_ms", "messaging-service"),
    ("integration_process", "write", "encrypt_ms", "messaging-service"),
    ("launcher", "write", "lookupService_ms", "messaging-service"),
    ("launcher", "write", "getCertificate_ms", "messaging-service"),
    ("launcher", "write", "post_ms", "messaging-service"),
    ("launcher", "write", "launcher_write_total_ms", "messaging-service"),
    ("digital_service", "post", "verifyCertificate_ms", "messaging-service"),
    ("digital_service", "post", "decrypt_ms", "messaging-service"),
    ("digital_service", "post", "storeLocalData_ms", "messaging-service"),

    ("launcher", "experimental_control", "validateServices_ms", ""),
    ("launcher", "start", "retrieveProgram_ms", ""),
    ("launcher", "start", "createCompartment_ms", ""),
    ("launcher", "start", "deploy_ms", ""),
    ("launcher", "start", "getIntegratedServices_ms", ""),
    ("launcher", "start", "exchangeKeys_ms", ""),
    ("launcher", "start", "generateAttestableDoc_ms", ""),
    ("launcher", "start", "generateCertificate_ms", ""),
    ("launcher", "start", "sign_ms", ""),
    ("launcher", "start", "run_ms", ""),
    ("launcher", "start", "start_total_ms", ""),
]

# Compilation is intentionally performed before the measured 30-run trusted
# campaign. A compile_ms entry carrying a campaign run_id therefore invalidates
# that run for the repeated-execution analysis.
TRUSTED_FORBIDDEN_METRICS = {"compile_ms", "execute_failed_ms"}
