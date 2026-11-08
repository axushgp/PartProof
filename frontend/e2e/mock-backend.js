/* eslint-disable @typescript-eslint/no-require-imports */
const http = require("node:http");

const PORT = 8000;

const MOCK_USER = {
  id: "user-auditor-1",
  email: "auditor@partproof.io",
  role: "auditor",
  is_active: true,
  created_at: new Date().toISOString(),
};

const PLAN_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

let tasks = [
  {
    id: "task-reconcile-88",
    user_id: MOCK_USER.id,
    title: "Orphaned Sandbox Audit",
    description: "Audit microVM unverified leak teardown state",
    status: "needs_reconciliation",
    created_at: new Date(Date.now() - 3600000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "task-blocked-99",
    user_id: MOCK_USER.id,
    title: "Unauthorized Egress Attempt",
    description: "Attempt network socket binding",
    status: "awaiting_approval",
    created_at: new Date(Date.now() - 7200000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "task-running-77",
    user_id: MOCK_USER.id,
    title: "Active Sandbox Simulation",
    description: "Executing mathematical model in isolated sandbox",
    status: "running",
    created_at: new Date(Date.now() - 10000).toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const plans = {
  "task-reconcile-88": {
    id: "plan-reconcile-88",
    task_id: "task-reconcile-88",
    model: "glm-5.3",
    plan_json: {
      steps: [
        {
          step_number: 1,
          description: "Verify cgroup isolation",
          code: "cat /proc/cgroups",
          execution_type: "subprocess",
        },
      ],
    },
    plan_hash: PLAN_HASH,
    policy_result: {
      allowed: true,
      policy_name: "default-sandbox-v1",
      policy_version: "1.0",
      network_mode: "none",
      cpu_limit: 1,
      memory_limit_mb: 512,
      timeout_seconds: 30,
      violations: [],
      evaluated_at: new Date().toISOString(),
    },
    policy_version: "1.0",
    approval_status: "approved",
    created_at: new Date().toISOString(),
  },
  "task-blocked-99": {
    id: "plan-blocked-99",
    task_id: "task-blocked-99",
    model: "glm-5.3",
    plan_json: {
      steps: [
        {
          step_number: 1,
          description: "Bind external socket",
          code: "nc -l -p 8080",
          execution_type: "subprocess",
        },
      ],
    },
    plan_hash: "f4b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b866",
    policy_result: {
      allowed: false,
      policy_name: "strict-airgap-v1",
      policy_version: "1.0",
      network_mode: "host",
      cpu_limit: 8,
      memory_limit_mb: 8192,
      timeout_seconds: 3600,
      violations: [
        "Network mode host violates airgap policy",
        "Command 'nc' matches forbidden executable rule",
      ],
      evaluated_at: new Date().toISOString(),
    },
    policy_version: "1.0",
    approval_status: "pending",
    created_at: new Date().toISOString(),
  },
  "task-running-77": {
    id: "plan-running-77",
    task_id: "task-running-77",
    model: "glm-5.3",
    plan_json: {
      steps: [
        {
          step_number: 1,
          description: "Run mathematical simulation",
          code: "python3 -c 'import time; time.sleep(60)'",
          execution_type: "subprocess",
        },
      ],
    },
    plan_hash: "77b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b877",
    policy_result: {
      allowed: true,
      policy_name: "default-sandbox-v1",
      policy_version: "1.0",
      network_mode: "none",
      cpu_limit: 1,
      memory_limit_mb: 512,
      timeout_seconds: 30,
      violations: [],
      evaluated_at: new Date().toISOString(),
    },
    policy_version: "1.0",
    approval_status: "approved",
    created_at: new Date().toISOString(),
  },
};

const executions = {
  "task-reconcile-88": {
    id: "exec-reconcile-88",
    task_id: "task-reconcile-88",
    status: "needs_reconciliation",
    worker_id: "reconciler-recovery-node-1",
    sandbox_id: "unverified-leak-sandbox-id-8888",
    cleanup_status: "leak_detected",
    started_at: new Date(Date.now() - 3600000).toISOString(),
    completed_at: new Date(Date.now() - 3550000).toISOString(),
    duration_seconds: 50.0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  "task-running-77": {
    id: "exec-running-77",
    task_id: "task-running-77",
    status: "running",
    worker_id: "worker-node-alpha",
    sandbox_id: "guest-microsandbox-prod-77",
    cleanup_status: "untracked",
    started_at: new Date(Date.now() - 5000).toISOString(),
    completed_at: null,
    duration_seconds: 5.0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;
  const method = req.method;

  // Set standard CORS & JSON headers
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (method === "OPTIONS") {
    res.statusCode = 204;
    res.end();
    return;
  }

  let body = "";
  req.on("data", (chunk) => {
    body += chunk;
  });

  req.on("end", () => {
    try {
      // 1. Auth Login
      if (method === "POST" && path === "/api/v1/auth/login") {
        const parsed = body ? JSON.parse(body) : {};
        if (parsed.email === "auditor@partproof.io" && parsed.password === "PartProofSecureDemo2026!") {
          res.statusCode = 200;
          res.end(
            JSON.stringify({
              access_token: "mock-jwt-token-partproof",
              token_type: "bearer",
              user: MOCK_USER,
            })
          );
        } else {
          res.statusCode = 401;
          res.end(JSON.stringify({ detail: "Invalid email or password." }));
        }
        return;
      }

      // 2. Auth Me
      if (method === "GET" && path === "/api/v1/auth/me") {
        const auth = req.headers.authorization;
        if (auth && auth.includes("mock-jwt-token-partproof")) {
          res.statusCode = 200;
          res.end(JSON.stringify(MOCK_USER));
        } else {
          res.statusCode = 401;
          res.end(JSON.stringify({ detail: "Unauthorized" }));
        }
        return;
      }

      // 3. Health & System Status
      if (method === "GET" && path === "/api/v1/health") {
        res.statusCode = 200;
        res.end(
          JSON.stringify({
            status: "healthy",
            version: "0.1.0",
            environment: "test",
            database_connected: true,
            sandbox_backend: "microsandbox",
          })
        );
        return;
      }

      if (method === "GET" && path === "/api/v1/system/status") {
        res.statusCode = 200;
        res.end(
          JSON.stringify({
            status: "ready",
            environment: "test",
            vultr_inference_configured: true,
            vultr_inference_model: "glm-5.3",
            sandbox_backend: "microsandbox",
            sandbox_ready: true,
            database_connected: true,
            active_sandboxes: 0,
            max_concurrent_sandboxes: 1,
            security_invariants: {
              network_disabled_by_default: true,
              credentials_in_sandbox: false,
              max_memory_mb: 1024,
              max_cpus: 1,
              max_timeout_seconds: 120,
              ephemeral_sandboxes: true,
              automatic_cleanup: true,
            },
          })
        );
        return;
      }

      if (method === "GET" && path === "/api/v1/system/inference") {
        res.statusCode = 200;
        res.end(
          JSON.stringify({
            status: "reachable",
            model: "glm-5.3",
            latency_ms: 120,
            message: "Vultr serverless inference online",
          })
        );
        return;
      }

      // 4. Tasks list & creation
      if (method === "GET" && path === "/api/v1/tasks") {
        res.statusCode = 200;
        res.end(JSON.stringify(tasks));
        return;
      }

      if (method === "POST" && path === "/api/v1/tasks") {
        const parsed = JSON.parse(body);
        const newTaskId = `task-${Date.now()}`;

        const newTask = {
          id: newTaskId,
          user_id: MOCK_USER.id,
          title: parsed.title || "SHA-256 Binary Integrity Verification",
          description: parsed.description,
          status: "awaiting_approval",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };

        tasks.unshift(newTask);

        plans[newTaskId] = {
          id: `plan-${newTaskId}`,
          task_id: newTaskId,
          model: "glm-5.3",
          plan_json: {
            steps: [
              {
                step_number: 1,
                description: "Compute cryptographic hashes",
                code: "sha256sum /guest/input.txt",
                execution_type: "subprocess",
              },
            ],
          },
          plan_hash: PLAN_HASH,
          policy_result: {
            allowed: true,
            policy_name: "default-sandbox-v1",
            policy_version: "1.0",
            network_mode: "none",
            cpu_limit: 1,
            memory_limit_mb: 512,
            timeout_seconds: 30,
            violations: [],
            evaluated_at: new Date().toISOString(),
          },
          policy_version: "1.0",
          approval_status: "pending",
          created_at: new Date().toISOString(),
        };

        res.statusCode = 201;
        res.end(
          JSON.stringify({
            task: newTask,
            plan: plans[newTaskId],
            execution: null,
            latest_execution: null,
            latest_approval: null,
            events: [],
            artifacts: [],
          })
        );
        return;
      }

      // 5. Task Detail
      const taskDetailMatch = path.match(/^\/api\/v1\/tasks\/([^/]+)$/);
      if (method === "GET" && taskDetailMatch) {
        const taskId = taskDetailMatch[1];
        const task = tasks.find((t) => t.id === taskId);
        if (!task) {
          res.statusCode = 404;
          res.end(JSON.stringify({ detail: "Task not found" }));
          return;
        }

        const plan = plans[taskId] || null;
        const execution = executions[taskId] || null;
        const artifacts =
          task.status === "succeeded"
            ? [
                {
                  id: `art-${taskId}`,
                  task_id: taskId,
                  execution_id: execution ? execution.id : "exec-1",
                  filename: "verification-report.json",
                  mime_type: "application/json",
                  size_bytes: 4096,
                  sha256: "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
                  created_at: new Date().toISOString(),
                },
              ]
            : [];

        const events = [
          {
            id: `evt-1-${taskId}`,
            execution_id: execution ? execution.id : "exec-1",
            event_type: "created",
            message: "Task created and policy evaluated",
            data: {},
            timestamp: task.created_at,
          },
        ];

        if (task.status === "succeeded") {
          events.push({
            id: `evt-2-${taskId}`,
            execution_id: execution ? execution.id : "exec-1",
            event_type: "completed",
            message: "MicroVM verified destroyed cleanly",
            data: {},
            timestamp: new Date().toISOString(),
          });
        }

        res.statusCode = 200;
        res.end(
          JSON.stringify({
            task,
            plan,
            execution,
            latest_execution: execution,
            events,
            artifacts,
          })
        );
        return;
      }

      // 6. Approve Task
      const approveMatch = path.match(/^\/api\/v1\/tasks\/([^/]+)\/approve$/);
      if (method === "POST" && approveMatch) {
        const taskId = approveMatch[1];
        const task = tasks.find((t) => t.id === taskId);
        if (!task) {
          res.statusCode = 404;
          res.end(JSON.stringify({ detail: "Task not found" }));
          return;
        }

        // Transition task to succeeded for deterministic test flow
        task.status = "succeeded";
        task.updated_at = new Date().toISOString();

        executions[taskId] = {
          id: `exec-${taskId}`,
          task_id: taskId,
          status: "succeeded",
          worker_id: "worker-node-alpha",
          sandbox_id: "guest-microsandbox-prod-42",
          cleanup_status: "verified_destroyed",
          started_at: new Date(Date.now() - 5000).toISOString(),
          completed_at: new Date().toISOString(),
          duration_seconds: 5.2,
          steps: [
            {
              id: `step-1-${taskId}`,
              task_id: taskId,
              execution_id: `exec-${taskId}`,
              step_number: 1,
              description: "Compute cryptographic hashes",
              execution_type: "subprocess",
              code: "sha256sum /guest/input.txt",
              status: "succeeded",
              exit_code: 0,
              stdout: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 /guest/input.txt",
              stderr: "",
              started_at: new Date(Date.now() - 5000).toISOString(),
              completed_at: new Date().toISOString(),
            },
          ],
          receipt_json: {
            task_id: taskId,
            execution_id: `exec-${taskId}`,
            sandbox_id: "guest-microsandbox-prod-42",
            status: "succeeded",
            runtime_image: "python:3.12-slim",
            guest_kernel: "vmlinux-6.6",
            cpu_limit: 1,
            memory_limit_mb: 512,
            network_mode: "none",
            plan_hash: PLAN_HASH,
            policy_name: "default-sandbox-v1",
            policy_version: "1.0",
            steps_executed: 1,
            steps_failed: 0,
            exit_code: 0,
            duration_seconds: 5.2,
            started_at: new Date(Date.now() - 5000).toISOString(),
            completed_at: new Date().toISOString(),
            verification_hash: "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            security_verified: true,
            signature: "sig_7f83b1657ff1fc53",
          },
          created_at: new Date(Date.now() - 5000).toISOString(),
          updated_at: new Date().toISOString(),
        };

        res.statusCode = 200;
        res.end(
          JSON.stringify({
            task,
            plan: plans[taskId],
            execution: executions[taskId],
            latest_execution: executions[taskId],
            events: [
              {
                id: `evt-comp-${taskId}`,
                execution_id: `exec-${taskId}`,
                event_type: "completed",
                message: "MicroVM verified destroyed cleanly",
                data: {},
                timestamp: new Date().toISOString(),
              },
            ],
            artifacts: [
              {
                id: `art-${taskId}`,
                task_id: taskId,
                execution_id: `exec-${taskId}`,
                filename: "verification-report.json",
                mime_type: "application/json",
                size_bytes: 4096,
                sha256: "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
                created_at: new Date().toISOString(),
              },
            ],
          })
        );
        return;
      }

      // 7. Cancel Task
      const cancelMatch = path.match(/^\/api\/v1\/tasks\/([^/]+)\/cancel$/);
      if (method === "POST" && cancelMatch) {
        const taskId = cancelMatch[1];
        const task = tasks.find((t) => t.id === taskId);
        if (!task) {
          res.statusCode = 404;
          res.end(JSON.stringify({ detail: "Task not found" }));
          return;
        }

        task.status = "cancelled";
        task.updated_at = new Date().toISOString();

        res.statusCode = 200;
        res.end(
          JSON.stringify({
            task,
            plan: plans[taskId],
            execution: executions[taskId] || null,
            latest_execution: executions[taskId] || null,
            events: [],
            artifacts: [],
          })
        );
        return;
      }

      // 8. Regenerate Task Plan
      const regenMatch = path.match(/^\/api\/v1\/tasks\/([^/]+)\/plan$/);
      if (method === "POST" && regenMatch) {
        const taskId = regenMatch[1];
        const task = tasks.find((t) => t.id === taskId);
        if (!task) {
          res.statusCode = 404;
          res.end(JSON.stringify({ detail: "Task not found" }));
          return;
        }

        const newHash = "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0";
        plans[taskId] = {
          id: `plan-regen-${Date.now()}`,
          task_id: taskId,
          model: "glm-5.3",
          plan_json: {
            title: task.title,
            summary: "Regenerated deterministic execution plan",
            reasoning_summary: "Refined plan structure following review",
            steps: [
              {
                step_id: "step-1",
                step_number: 1,
                description: "Compute regenerated cryptographic hashes",
                code: "sha256sum /guest/input.txt",
                execution_type: "subprocess",
              },
            ],
            required_capabilities: [],
            network_required: false,
            success_criteria: ["Hashes match canonical digests"],
            expected_artifacts: ["verification-report.json"],
          },
          plan_hash: newHash,
          policy_result: {
            allowed: true,
            policy_name: "default-sandbox-v1",
            policy_version: "1.0",
            network_mode: "none",
            cpu_limit: 1,
            memory_limit_mb: 512,
            timeout_seconds: 30,
            violations: [],
            evaluated_at: new Date().toISOString(),
          },
          policy_version: "1.0",
          approval_status: "pending",
          created_at: new Date().toISOString(),
        };

        task.status = "awaiting_approval";
        task.updated_at = new Date().toISOString();

        res.statusCode = 200;
        res.end(JSON.stringify(plans[taskId]));
        return;
      }

      // Fallback 404
      res.statusCode = 404;
      res.end(JSON.stringify({ detail: `Route not found: ${method} ${path}` }));
    } catch (err) {
      res.statusCode = 500;
      res.end(JSON.stringify({ detail: String(err) }));
    }
  });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`PartProof Mock API Server running on http://127.0.0.1:${PORT}`);
});
