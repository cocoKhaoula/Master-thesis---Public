# Cross-Layer Context for LLM-Based Detection and Root-Cause Analysis of Configuration Anomalies in AWS Lambda

This repository holds the experiment code for the master's thesis *"Cross-Layer Context for LLM-Based Detection and Root-Cause Analysis of Configuration Anomalies in AWS Lambda: An Ablation Study"* by Khaoula Khazri (Transport and Telecommunication Institute, Riga, 2026).

The experiment checks whether an LLM agent finds the root cause of configuration anomalies in AWS Lambda more accurately when it gets **IAM, IaC and code context** on top of telemetry. It runs a controlled ablation (L0–L4) on a labelled fault-injection dataset and compares the agent with threshold alarms, Isolation Forest and CloudFormation drift detection.

## Repository structure

```
app/                      Benchmark application: 4 SeBS functions + AWS SAM template (thesis 3.4, Table 3.2)
  template.yaml           Intended state: functions, one IAM role per function, S3 buckets, DynamoDB table
  functions/              130.crud-api, 120.uploader, 210.thumbnailer, 311.compression
config/
  experiment.yaml         Every fixed variable of the experiment (windows, model, prices, baselines ...)
  ablation_levels.yaml    L0-L4: which MCP servers and custom tools each level gets (Table 2.3, Table 3.1)
iam/
  agent-readonly-policy.json   Read-only agent role (requirement R4, Section 5.7)
  harness-policy.json          Harness role: inject/revert faults, drift detection
src/lambda_rca/
  harness/                Fault injection and labelling (Chapter 4, Appendix A)
    faults.py             F1-F6: inject + exact revert
    campaign.py           Window plan, steady state -> fault -> recovery cycle, labels
    policy.py             Pure policy/template transformations (unit-tested)
    snapshot.py           Live-config snapshots + CloudFormation drift detection per window
    apprepo.py            The app's own git repo + `sam deploy` (committed faults, F5)
    loadgen.py            Constant-rate load generator, seed inputs
  agent/                  LLM agent (Chapter 3)
    runner.py             Strands Agents + Claude on Bedrock, MCP servers per level, token logging
    prompt.py             Prompt (Appendix B)
    schema.py             Output JSON schema and parsing (Appendix C)
    rawlogs.py            Raw logs for L0
    tools/                Custom IaC-template and code/git tools, pinned to the window end
  baselines/              Threshold alarms, Isolation Forest, CloudFormation drift (Chapter 6)
  evaluation/             Metrics (Section 2.6, Appendix F), tables, figures (Chapter 7)
  labels.py               Label schema (Table 4.2) and matching rules for Level-1/Level-2 RCA
  cli.py                  `lambda-rca` command line
tests/                    Unit tests, including the worked example of Table F.1
data/                     The dataset (published, R7): labels, snapshots, metrics, agent runs, baselines
results/                  Tables (CSV/Markdown) and figures produced by `lambda-rca evaluate` / `plots`
```

## Requirements

- Python 3.11+, git
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) and AWS CLI v2
- A **dedicated AWS test account** (the experiment runs in **eu-north-1**)
- An **Anthropic API key** for the agent model (Claude Haiku 5.5), saved as the user environment variable `ANTHROPIC_API_KEY` (`setx ANTHROPIC_API_KEY "..."` on Windows). Amazon Bedrock is supported through `agent.provider: bedrock` but was not usable on the experiment account.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -e ".[agent,dev]"
pytest                          # offline unit tests, no AWS needed
```

The two official AWS MCP servers are installed once into their own environment, which pins their versions (recorded in Appendix G):

```bash
python -m venv .mcp-venv
.mcp-venv\Scripts\python -m pip install awslabs.cloudwatch-mcp-server==0.3.1 awslabs.iam-mcp-server==1.1.2
```

## AWS setup (once)

Use two named profiles in `~/.aws/config`. The repository never stores credentials.

| Profile | Purpose | Policy |
|---|---|---|
| `rca-harness` | deploy the stack, inject and revert faults, run drift detection | `iam/harness-policy.json`, plus deployment rights for `sam deploy` (admin in the test account is fine) |
| `rca-agent` | the agent and its MCP servers, read-only | `iam/agent-readonly-policy.json` |

The agent profile can be a role that the harness user assumes (`role_arn` + `source_profile` in `~/.aws/config`). Region, model and prices are set in `config/experiment.yaml`.

## Running the experiment

Each step maps to a phase in Section 2.5 / 3.7 of the thesis.

```bash
lambda-rca init-app-repo        # 1. create workspace/app-repo (the app's own git history)
lambda-rca deploy               #    sam build + deploy with the harness profile
lambda-rca seed                 #    upload input image/files
lambda-rca show-tools           #    check which tools each ablation level gets
```

Long-running commands are started as independent background processes with `scripts/start.ps1`, so they keep running when the terminal or editor is closed. Output goes to `logs/<command>.log`, and `scripts/stop.ps1 <command>` stops them:

```bash
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 loadgen
```

```bash
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 steady-state --minutes 30
```

```bash
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 campaign --only W002,W005,W007 --reps 1
```

```bash
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 campaign
```

The first starts the load generator, which runs for the whole campaign; the second records the Isolation Forest training data; the third is the pilot; the fourth is the full campaign. Then:

```bash
lambda-rca baselines            # threshold, Isolation Forest, drift on the same windows
lambda-rca evaluate             # metrics -> results/*.csv, results/results.md
lambda-rca plots                # figures for Chapter 7
```

The campaign has 95 windows (60 symptomatic, 15 silent drift, 20 normal) and runs the agent at 5 levels with 1 repetition per window (475 runs, about 40 h). F4 windows are postponed automatically while the account's Lambda concurrency quota is too low for reserved concurrency.

Other commands:
- `lambda-rca plan` prints the 95 planned windows.
- `lambda-rca campaign --ttd` adds the agent time-to-detect polling runs.
- `lambda-rca recover` reverts a fault left active after a crash or Ctrl-C.

The campaign is resumable: windows that already have a label are skipped, and so are agent runs that already have an output file.

> Run `lambda-rca baselines` within **15 days** of the campaign. CloudWatch keeps 1-minute metrics only for 15 days. After the first run the metrics are cached in `data/metrics/`.

## Design notes (please reflect these in the thesis text)

1. **The agent runs while the fault is still active ("hold" mode).** The IAM tools and the live-configuration tool read the *current* AWS state. If the agent analysed a window after the revert, it would see the restored configuration, and the IAM/IaC layers would carry no information. So each window runs: inject → 10-min window → drift check (at minute 8) and snapshot → agent runs for L0–L4 × 1 rep → revert → 10-min recovery. The telemetry the agent queries is still limited to the fixed window `[start, end]`. Section 3.1 currently says that "the agent analyses windows after they are recorded"; it should describe this order instead.
2. **The code tool is pinned to the window end.** It only shows commits made before the end of the window, so a later `git revert` of an F5 fault cannot leak into the analysis.
3. **Window IDs are neutral** (`W001` …). The agent gets only the ID and the time range (`data/labels/windows.jsonl`). Labels stay in `labels.jsonl` and are never passed to the agent.
4. **Benign commits** (README notes) go into the app repo every 4 windows, so "the last commit is the fault" is not a shortcut at L4.
5. **Matching rules are fixed before the runs.** Each label stores `accepted_layers` (Level 1) and `artifact_match` tokens (Level 2), for example `["putitem"]` for F1 or the short commit hash for F5. Level 2 also requires the correct function, because e.g. `OUTPUT_BUCKET` exists in three functions. Level 1 does not depend on k, because layer and function are single fields of the answer.
6. **Isolation Forest and constant features.** In steady state, `errors` and `throttles` are always 0, and a tree can never split on a constant feature. Without a fix the model would be blind to exactly these symptoms. A negligible jitter (σ = 10⁻³) is added to constant training features (`baselines/iforest.py`). Section 5.5 should mention this.
7. **Threshold alarms** are evaluated offline on the 1-minute metrics with CloudWatch alarm semantics (2 of 3 datapoints breaching). This keeps them identical across windows and reproducible.
8. **F2 on `crud-api`** may cause no symptom, because DynamoDB calls are fast even at 128 MB / 3 s. Check this in the pilot and adjust `faults.F2` or the plan if needed.

## Mapping to the thesis

| Thesis | Code |
|---|---|
| Table 2.1 R1 (automatic labels) | `harness/campaign.py`, `labels.py` |
| R2 (revert, no overlap) | `harness/faults.py` (saved originals), `campaign.py` (`finally`, `recover`) |
| R3 (switch context per level) | `config/ablation_levels.yaml`, `agent/runner.py` |
| R4 (read-only) | `iam/agent-readonly-policy.json`, `--readonly` MCP flags, blocked tool prefixes |
| R5 (JSON answer) | `agent/schema.py` |
| R6 (token usage) | `agent/runner.py` → `usage` in every run file |
| R7 (publish) | this repository + `data/` |
| Eq. 2.1–2.6, Appendix F | `evaluation/metrics.py`, `tests/test_metrics.py` |
| Appendix A | `harness/faults.py` |
| Appendix B / C | `agent/prompt.py` / `agent/schema.py` |

## Data layout

```
data/labels/labels.jsonl       ground truth (Table 4.2 + matching rules)
data/labels/windows.jsonl      window ids and time ranges (what the agent sees)
data/labels/steady_state.json  Isolation Forest training period
data/snapshots/W###.json       live configuration of all functions at the end of each window
data/metrics/W###.csv          per-minute CloudWatch metrics
data/runs/L#/W###_r#.json      agent answer, tool calls, tokens, latency per run
data/baselines/*.jsonl         baseline predictions; cfn_drift/W###.json raw drift results
```
9. **Model and sampling.** The agent uses Claude Haiku 5.5 through the Anthropic API, with prompt caching. Claude 5.5 models reject sampling parameters, so the model's default sampling is used instead of temperature 0; run-to-run variation is covered by the repetitions. Cached input tokens are counted in the token totals and priced separately in the cost analysis.
10. **IaC layer.** The AWS CloudFormation MCP server was withdrawn, and its successor (`awslabs.aws-iac-mcp-server`) only validates templates and searches documentation. Level L3 therefore uses two custom read-only tools: `read_iac_template` (intended state) and `read_live_configuration` (live Lambda configuration through the read-only role).
11. **Region.** The organization's region policy only allows eu-north-1, so the stack, the agent role and all measurements are in eu-north-1.
