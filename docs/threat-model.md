# PartProof Threat Model

## 1. Scope & Objective
PartProof executes untrusted, AI-generated Python code and processes potentially adversarial third-party input documents (such as vendor quotes, bills of materials, or test scripts). The objective of this threat model is to formally articulate the trust boundaries, threat actors, attack vectors, and specific security controls deployed to achieve **zero blast radius**.

---

## 2. Trust Boundaries

```
[ UNTRUSTED ] Web Users & Third-Party Datasets
       |
=== BOUNDARY 1: HTTPS & Authentication Gateway ===
       |
[ TRUSTED ] PartProof FastAPI Control Plane (Host Linux User: linuxuser)
       |
=== BOUNDARY 2: External API Authentication (Vultr Inference Key) ===
       |
[ TRUSTED EXTERNAL ] Vultr Serverless Inference API (glm-5.3)
       |
=== BOUNDARY 3: Hardware Virtualization / KVM Device (/dev/kvm) ===
       |
[ UNTRUSTED EXECUTION ] Ephemeral MicroVM (libkrun, Guest Kernel 6.12.113)
```

---

## 3. Threat Actors & Vectors

| Threat ID | Threat Vector | Description | PartProof Mitigation |
|---|---|---|---|
| **T-01** | Host File Exfiltration | Generated or injected code attempts to read sensitive host files (`/etc/shadow`, `~/.ssh`, `.env`, database). | Hardware-isolated guest filesystem. The microVM runs on a standalone sparse image; host rootfs is completely invisible and unmounted. |
| **T-02** | Credential Scraping | Code attempts to inspect environment variables (`os.environ`) to harvest `VULTR_INFERENCE_API_KEY` or DB credentials. | Zero credentials injected. Environment variables are stripped. API keys live exclusively in the host FastAPI memory space. |
| **T-03** | Command & Control / Data Exfiltration | Malicious code attempts outbound TCP/UDP connections to exfiltrate data or download secondary attack payloads. | Hard network denial (`Network.none()`). Guest connections to external IPs fail immediately (`ECONNREFUSED` / no default route). |
| **T-04** | Resource Exhaustion (DoS) | Script spawns a fork bomb (`while True: os.fork()`) or allocates gigabytes of RAM to crash the Vultr VM. | Strict cgroup and microVM bounds: 1 vCPU, 512MB RAM cap, and hard process execution timeout (e.g. 30-120 seconds max). |
| **T-05** | Host Kernel Exploit / Container Breakout | Exploit targeting Linux container namespaces/cgroups to escape to host ring 0. | Microsandbox uses distinct guest kernels (`libkrun` + KVM) rather than shared container namespaces. A guest kernel crash does not compromise host ring 0. |
| **T-06** | Prompt Injection via Vendor Data | Input files (e.g. BOM descriptions) contain adversarial prompt injection instructions trying to alter agent logic. | Strict schema enforcement (`Pydantic v2`), deterministic policy engine gating, and mandatory user approval before code dispatch. |
| **T-07** | Orphaned Sandbox Leak | MicroVM continues running after error, consuming compute and storage over time. | Context-managed `finally` destruction blocks and background cleanup sweeps ensuring `msb ls` returns zero sandboxes. |
