#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/file.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <openssl/ssl.h>
#include <openssl/err.h>

#define HEALTH_REGISTRY_SERVICE_ID "health-registry-service"
#define HOSPITAL_SERVICE_ID "hospital-service"
#define MESSAGING_SERVICE_ID "messaging-service"

static char program_id[64] = "1";
static char current_run_id[160] = "";
static FILE *metrics_fp = NULL;

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
}

static long long epoch_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (long long)ts.tv_sec * 1000LL + (long long)ts.tv_nsec / 1000000LL;
}

static void ensure_metrics_file(void) {
    if (metrics_fp) return;
    const char *path = getenv("METRICS_FILE");
    if (!path) path = "/tmp/all_metrics.csv";
    metrics_fp = fopen(path, "a+");
    if (!metrics_fp) return;

    flock(fileno(metrics_fp), LOCK_EX);
    fseek(metrics_fp, 0, SEEK_END);
    if (ftell(metrics_fp) == 0) {
        fprintf(metrics_fp, "ts,run_id,component,operation,metric,value_ms,program_id,service_id\n");
        fflush(metrics_fp);
    }
    flock(fileno(metrics_fp), LOCK_UN);
}

static void metric(const char *operation, const char *metric_name, double value_ms, const char *service_id) {
    ensure_metrics_file();
    if (metrics_fp) {
        flock(fileno(metrics_fp), LOCK_EX);
        fprintf(metrics_fp, "%lld,%s,integration_process,%s,%s,%.6f,%s,%s\n",
                epoch_ms(), current_run_id, operation, metric_name, value_ms,
                program_id, service_id ? service_id : "");
        fflush(metrics_fp);
        flock(fileno(metrics_fp), LOCK_UN);
    }
}

static SSL_CTX *initialize_ssl_context(void) {
    OpenSSL_add_all_algorithms();
    SSL_load_error_strings();
    const SSL_METHOD *method = TLS_client_method();
    SSL_CTX *ctx = SSL_CTX_new(method);
    if (!ctx) ERR_print_errors_fp(stderr);
    return ctx;
}

static void cleanup_ssl(SSL *ssl, SSL_CTX *ctx) {
    if (ssl) { SSL_shutdown(ssl); SSL_free(ssl); }
    if (ctx) SSL_CTX_free(ctx);
}

static char *http_post_json(const char *host, const char *port, const char *endpoint, const char *json_body) {
    SSL_CTX *ctx = NULL;
    SSL *ssl = NULL;
    int server = -1;
    struct sockaddr_in addr;
    char request[16384];
    char buffer[4096];
    size_t total = 0;
    char *response = NULL;

    ctx = initialize_ssl_context();
    if (!ctx) goto cleanup;
    server = socket(AF_INET, SOCK_STREAM, 0);
    if (server < 0) goto cleanup;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(atoi(port));
    if (inet_pton(AF_INET, host, &addr.sin_addr) != 1) goto cleanup;
    if (connect(server, (struct sockaddr *)&addr, sizeof(addr)) < 0) goto cleanup;
    ssl = SSL_new(ctx);
    if (!ssl) goto cleanup;
    SSL_set_fd(ssl, server);
    if (SSL_connect(ssl) <= 0) goto cleanup;

    snprintf(request, sizeof(request),
             "POST %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n%s",
             endpoint, host, strlen(json_body), json_body);
    if (SSL_write(ssl, request, (int)strlen(request)) <= 0) goto cleanup;

    while (1) {
        int n = SSL_read(ssl, buffer, sizeof(buffer));
        if (n <= 0) break;
        char *tmp = realloc(response, total + (size_t)n + 1);
        if (!tmp) { free(response); response = NULL; break; }
        response = tmp;
        memcpy(response + total, buffer, (size_t)n);
        total += (size_t)n;
        response[total] = '\0';
    }

cleanup:
    if (server >= 0) close(server);
    cleanup_ssl(ssl, ctx);
    return response;
}

static int http_status_code(const char *response) {
    int status = 0;
    if (response) sscanf(response, "HTTP/%*s %d", &status);
    return status;
}

static char *extract_http_json_body(const char *response) {
    if (!response) return NULL;
    const char *body = strstr(response, "\r\n\r\n");
    return strdup(body ? body + 4 : response);
}

static const char *skip_ws(const char *p) {
    while (p && (*p == ' ' || *p == 9 || *p == 10 || *p == 13)) p++;
    return p;
}

static char *json_get_string(const char *json, const char *key) {
    if (!json || !key) return NULL;
    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char *p = strstr(json, pattern);
    if (!p) return NULL;
    p += strlen(pattern);
    p = strchr(p, ':');
    if (!p) return NULL;
    p = skip_ws(p + 1);
    if (*p != '"') return NULL;
    p++;

    size_t cap = strlen(p) + 1;
    char *out = malloc(cap);
    if (!out) return NULL;
    size_t j = 0;
    for (; *p; ++p) {
        if (*p == '"') { out[j] = '\0'; return out; }
        if (*p == '\\') {
            ++p;
            if (!*p) break;
            switch (*p) {
                case '"': out[j++] = '"'; break;
                case '\\': out[j++] = '\\'; break;
                case '/': out[j++] = '/'; break;
                case 'b': out[j++] = '\b'; break;
                case 'f': out[j++] = '\f'; break;
                case 'n': out[j++] = '\n'; break;
                case 'r': out[j++] = '\r'; break;
                case 't': out[j++] = '\t'; break;
                default: out[j++] = *p; break;
            }
        } else out[j++] = *p;
    }
    free(out);
    return NULL;
}

static char *json_escape(const char *input) {
    if (!input) return strdup("");
    size_t len = strlen(input);
    char *out = malloc((len * 2) + 1);
    if (!out) return NULL;
    size_t j = 0;
    for (size_t i = 0; i < len; ++i) {
        unsigned char c = (unsigned char)input[i];
        switch (c) {
            case '"': out[j++] = '\\'; out[j++] = '"'; break;
            case '\\': out[j++] = '\\'; out[j++] = '\\'; break;
            case '\n': out[j++] = '\\'; out[j++] = 'n'; break;
            case '\r': out[j++] = '\\'; out[j++] = 'r'; break;
            case '\t': out[j++] = '\\'; out[j++] = 't'; break;
            default: out[j++] = (char)c; break;
        }
    }
    out[j] = '\0';
    return out;
}

static const char *getServicePublicKey(const char *srv_id) {
    (void)srv_id;
    return "simulated-service-public-key";
}

static char *encrypt_dataset(const char *public_key, const char *data) {
    (void)public_key;
    return data ? strdup(data) : NULL;
}

static char *decrypt_dataset(const char *data_enc) {
    return data_enc ? strdup(data_enc) : NULL;
}

static void initialise_run_id(void) {
    const char *run_env = getenv("RUN_ID");
    if (run_env && *run_env) {
        strncpy(current_run_id, run_env, sizeof(current_run_id) - 1);
        current_run_id[sizeof(current_run_id) - 1] = '\0';
        return;
    }
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    snprintf(current_run_id, sizeof(current_run_id), "%lld-%ld-%ld",
             (long long)ts.tv_sec, ts.tv_nsec, (long)getpid());
}


static char *extract_json_string(const char *data, const char *key) {
    return json_get_string(data, key);
}

#define LAUNCHER_HOST "127.0.0.1"
#define LAUNCHER_PORT "5000"

static char *read_action(const char *srv_id, const char *patient_id) {
    double t0 = now_ms();
    char endpoint[256];
    char payload[512];
    snprintf(endpoint, sizeof(endpoint), "/api/read/%s/%s", srv_id, program_id);
    snprintf(payload, sizeof(payload), "{\"runId\":\"%s\",\"patientId\":\"%s\"}", current_run_id, patient_id);

    char *response = http_post_json(LAUNCHER_HOST, LAUNCHER_PORT, endpoint, payload);
    int status = http_status_code(response);
    if (!response || status < 200 || status >= 300) {
        fprintf(stderr, "Read_act failed for %s (HTTP %d)\n", srv_id, status);
        free(response);
        return NULL;
    }

    char *body = extract_http_json_body(response);
    free(response);
    if (!body) return NULL;
    char *data_enc = json_get_string(body, "dataEnc");
    free(body);
    if (!data_enc) {
        fprintf(stderr, "Read_act failed for %s: response has no dataEnc\n", srv_id);
        return NULL;
    }

    double td = now_ms();
    char *plain = decrypt_dataset(data_enc);
    double decrypt_ms = now_ms() - td;
    free(data_enc);
    if (!plain) return NULL;
    double total_ms = now_ms() - t0;
    metric("read", "decrypt_ms", decrypt_ms, srv_id);
    metric("read", "read_act_total_ms", total_ms, srv_id);
    return plain;
}

static int write_action(const char *srv_id, const char *data) {
    double t0 = now_ms();
    double tk = now_ms();
    const char *puK = getServicePublicKey(srv_id);
    double get_key_ms = now_ms() - tk;

    double te = now_ms();
    char *data_enc = encrypt_dataset(puK, data);
    double encrypt_ms = now_ms() - te;
    if (!data_enc) return -1;

    char *data_json = json_escape(data_enc);
    if (!data_json) { free(data_enc); return -1; }
    char payload[16384];
    char endpoint[256];
    snprintf(payload, sizeof(payload), "{\"dataEnc\":\"%s\",\"runId\":\"%s\"}", data_json, current_run_id);
    free(data_json);
    snprintf(endpoint, sizeof(endpoint), "/api/write/%s/%s", srv_id, program_id);

    double tr = now_ms();
    char *response = http_post_json(LAUNCHER_HOST, LAUNCHER_PORT, endpoint, payload);
    double request_ms = now_ms() - tr;
    int status = http_status_code(response);
    free(response);
    free(data_enc);
    if (status < 200 || status >= 300) {
        fprintf(stderr, "Write_act failed for %s (HTTP %d)\n", srv_id, status);
        return -1;
    }

    double total_ms = now_ms() - t0;
    metric("write", "getServicePublicKey_ms", get_key_ms, srv_id);
    metric("write", "encrypt_ms", encrypt_ms, srv_id);
    metric("write", "write_request_response_ms", request_ms, srv_id);
    metric("write", "write_act_total_ms", total_ms, srv_id);
    return 0;
}

static int process_business_flow(const char *requested_patient_id) {
    /* Business precondition: the Hospital Service has requested this patient. */
    char *patient_json = read_action(HEALTH_REGISTRY_SERVICE_ID, requested_patient_id);
    if (!patient_json) {
        fprintf(stderr, "Failed to retrieve patient data from Health Registry Service\n");
        return -1;
    }

    char *patient_id = extract_json_string(patient_json, "patientId");
    char *hospital_id = extract_json_string(patient_json, "hospitalId");
    if (!patient_id || !*patient_id || !hospital_id || !*hospital_id) {
        fprintf(stderr, "Patient data are missing patientId or hospitalId\n");
        free(patient_json); free(patient_id); free(hospital_id);
        return -1;
    }

    /* First Write_act: update the hospital patient record with the dataset
       retrieved from the Health Registry Service. */
    if (write_action(HOSPITAL_SERVICE_ID, patient_json) != 0) {
        free(patient_json); free(patient_id); free(hospital_id);
        return -1;
    }

    /* Second Write_act: notify hospital staff that the record is available. */
    char notification[2048];
    snprintf(notification, sizeof(notification),
             "{\"patientId\":\"%s\",\"hospitalId\":\"%s\",\"message\":\"Patient record updated and available.\"}",
             patient_id, hospital_id);
    if (write_action(MESSAGING_SERVICE_ID, notification) != 0) {
        free(patient_json); free(patient_id); free(hospital_id);
        return -1;
    }

    free(patient_json); free(patient_id); free(hospital_id);
    return 0;
}

int main(void) {
    const char *pid_env = getenv("PROGRAM_ID");
    if (pid_env && *pid_env) {
        strncpy(program_id, pid_env, sizeof(program_id) - 1);
        program_id[sizeof(program_id) - 1] = '\0';
    }
    initialise_run_id();

    const char *requested_patient_id = getenv("PATIENT_ID");
    if (!requested_patient_id || !*requested_patient_id) requested_patient_id = "P001";

    double t0 = now_ms();
    int rc = process_business_flow(requested_patient_id);
    double total_ms = now_ms() - t0;
    if (rc == 0) metric("execute", "execute_total_ms", total_ms, "");
    else metric("execute", "execute_failed_ms", total_ms, "");

    if (metrics_fp) fclose(metrics_fp);
    return rc == 0 ? 0 : 1;
}
