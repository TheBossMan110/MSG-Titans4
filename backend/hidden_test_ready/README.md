# hidden_test_ready/

The drop zone for the evaluators' **hidden complaint pack**. Put your file here (for example
`hidden_test_ready\hidden_complaints.csv`) and follow the steps below. Nothing in the application reads this
folder automatically: it is simply a documented, predictable place for the file, and the commands below point
at it.

The hidden pack goes through **exactly the same code path** as the team's own 500-complaint corpus: the same
importer, the same two pipelines, the same comparison engine and the same benchmark. No code or configuration
change is needed, and labels are optional.

---

## 1. File format

* **CSV** (UTF-8; the byte-order mark Excel writes is handled) or **XLSX** (first worksheet). Maximum 20 MB.
* One row per complaint, one header row. Header names are matched loosely: case is ignored and spaces or hyphens
  become underscores, so `Order Ref`, `order-ref` and `ORDER_REF` all mean `order_ref`.
* Columns the importer does not know (for example `tags`) are ignored.
* The browser import form accepts CSV. For XLSX, use the API command in section 3, or save the sheet from Excel
  as *CSV UTF-8*.

### Complaint columns

| Column | Required | Notes |
|---|---|---|
| `description` | **yes** | The complaint text. A row without it is skipped and reported with its row number; every other row is imported. Text beyond `MAX_COMPLAINT_LENGTH` (8,000 characters) is truncated and the truncation recorded. |
| `title` | recommended | One line. If empty, the first 80 characters of the description are used. |
| `external_ref` | no | Your own id for the row (for example `H-0001`). Lets `previous_ref` point at an earlier row. |
| `previous_ref` | no | The `external_ref` of an earlier row this one follows up (used for repeat-contact detection). |
| `order_ref` | no | Consignment or order reference. RaftarXpress uses `CN-` tracking numbers (also `FWD-` freight and `MER-` merchant); anything else is accepted and noted as unrecognised. |
| `transaction_ref` | no | Invoice or payment reference. |
| `product` | no | For example `Parcel Courier`. |
| `amount` | no | A number. `42500`, `42,500` and `Rs. 42,500` are all read as 42500. |
| `currency` | no | For example `PKR`. |
| `channel` | no | `WEB`, `EMAIL`, `CHAT`, `PHONE` or `UPLOAD`. Anything else, or blank, is stored as `IMPORT`. |
| `customer_email`, `customer_name` | no | Links rows from the same customer (needed for repeat detection across rows). |
| `customer_type` | no | For example `Individual Consumer`, `VIP/Premium Account`. |
| `requested_resolution` | no | What the customer asks for. |

Minimal example:

```csv
title,description
Parcel not delivered,"My parcel CN-44321908711 was due on Monday and tracking has not moved for four days."
```

### Optional ground-truth columns (only if you want accuracy scores)

If present, these are stored as labels and read **only by the benchmark**. A test (`tests/test_benchmark.py::
test_no_pipeline_can_read_a_ground_truth_label`) proves no pipeline can see them.

| Column (either name works) | Allowed values |
|---|---|
| `expected_category` / `expected_category_code` | `DELIVERY`, `LOST_SHIPMENT`, `PRODUCT_DEFECT`, `BILLING`, `REFUND`, `ACCOUNT`, `TECHNICAL_SUPPORT`, `STAFF_BEHAVIOR`, `WARRANTY`, `PRIVACY`, `SAFETY`, `CUSTOMS`, `SERVICE_QUALITY` |
| `expected_subcategory` / `expected_subcategory_code` | The 34 subcategory codes in `backend/config/taxonomy.yaml` (for example `DELAYED_DELIVERY`, `DUPLICATE_CHARGE`) |
| `expected_department` / `expected_department_code` | `LOGISTICS_OPS`, `BILLING`, `RETURNS_REFUNDS`, `WARRANTY_CLAIMS`, `CUSTOMER_RELATIONS`, `ACCOUNT_SECURITY`, `COMPLIANCE`, `SAFETY`, `MGMT_ESCALATIONS` |
| `expected_urgency` | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `expected_priority` / `expected_priority_code` | `P0`, `P1`, `P2`, `P3` |
| `expected_escalation` / `expected_escalation_code` | `NONE`, `SUPERVISOR`, `DEPT_MANAGER`, `SPECIALIST`, `COMPLIANCE_REVIEW`, `CRITICAL_MGMT` |

Values are upper-cased on import. If your labels use the corpus ids (`CAT-01`, `SUB-001`, `DEPT-01`), translate
them with `backend/config/raftarxpress_codes.json`. `dataset/raftarxpress/complaints/raftarxpress_benchmark.csv`
is a complete, labelled example in exactly this format.

---

## 2. Run it in the browser

1. **Wake the backend** (live site only): open https://supportnova.onrender.com/api/health and wait for
   `"status": "ok"` (up to about 50 seconds after idle).
2. **Sign in** at https://support-nova.vercel.app (or http://localhost:3000) as `evaluator@raftarxpress.com`
   (password `SupportNova#2026`) or as an administrator.
3. Open **`/dashboard/benchmark`** → **Import a dataset** → type a tag, for example `hidden-pack` (letters,
   digits, `_`, `.` and `-`; stored in capitals as `HIDDEN-PACK`) → **Continue**.
4. On the dataset page choose the CSV under *CSV file*, tick *Replace existing rows with this tag* if you are
   re-importing a corrected file, and click **Import**. You see how many rows were imported, labelled, unlabelled
   and skipped, with the reason for each skipped row. **Importing only stores the rows; nothing is analysed yet.**
5. Back on `/dashboard/benchmark`, under **Start a run**: choose the dataset, give the run a label and click
   **Start**.
   * **Rules only (fast, deterministic):** untick *Run GenAI (Pipeline 1) as well as the rules*. One run
     processes the whole file.
   * **Both pipelines:** keep *Run GenAI* ticked, set **Limit** to 25 to 50 and keep **Resume** ticked. Click
     **Start** again until *Pending* is 0. Each run continues where the last stopped, which is what lets a
     free-tier quota finish the file.
   * Choose one of the two per tag. After a rules-only run every complaint counts as analysed, so a later GenAI
     run with *Resume* finds nothing left to do (untick *Resume* to re-analyse everything).
6. **Read the results.**
   * Every complaint in the pack is now an ordinary complaint, processed exactly like a submitted one: routed, SLA
     clocks started, escalated, queued for review where needed. Browse them at
     `/dashboard/complaints?dataset_tag=HIDDEN-PACK` (or **Organisation → Datasets → Complaints**) and open any
     one for its **Why** tab: both pipelines' answers, the rules that fired and the policy trace.
   * **Reports** (manager or administrator): type the tag into the *Dataset tag* filter.
   * **If the file had labels:** open the run from the *Runs* table. It shows, per field, the accuracy of GenAI
     and of the rules (each over its own denominator) and how often they agreed, mandatory-escalation recall on
     its own line, latency (mean and p95), and the complaints the rules got wrong. An unlabelled pack is processed in full but produces no accuracy
     figures: the benchmark reports `null`, never an invented score.

## 3. Run it from PowerShell (API)

Run from the `backend` folder. Swap `$api` for `http://localhost:8000/api` when running locally.

```powershell
$api   = "https://supportnova.onrender.com/api"
$login = @{ email = "evaluator@raftarxpress.com"; password = "SupportNova#2026" } | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post -Uri "$api/auth/login" -ContentType "application/json" -Body $login).access_token
$auth  = @{ Authorization = "Bearer $token" }

# 1. Import (CSV or XLSX). replace=true clears the tag first, so a re-import never doubles the rows.
curl.exe -s -X POST "$api/benchmark/datasets/HIDDEN-PACK/import?replace=true" -H "Authorization: Bearer $token" -F "file=@hidden_test_ready\hidden_complaints.csv"

# 2. Counts: total, labelled, unlabelled, analysed, pending_analysis
Invoke-RestMethod -Uri "$api/benchmark/datasets/HIDDEN-PACK" -Headers $auth

# 3a. Rules only, whole file, one call
Invoke-RestMethod -Method Post -Uri "$api/benchmark/run?dataset_tag=HIDDEN-PACK&run_genai=false&label=hidden-rules" -Headers $auth -TimeoutSec 1800

# 3b. OR both pipelines, in resumable batches of 25
do {
    $run  = Invoke-RestMethod -Method Post -Uri "$api/benchmark/run?dataset_tag=HIDDEN-PACK&run_genai=true&limit=25&resume=true&label=hidden-genai" -Headers $auth -TimeoutSec 1800
    $left = (Invoke-RestMethod -Uri "$api/benchmark/datasets/HIDDEN-PACK" -Headers $auth).pending_analysis
    "Run $($run.id): $($run.sample_size) analysed, $left pending"
} while ($left -gt 0)

# 4. Results: every run, then one run in detail (per-field metrics, escalation recall, rule failures)
Invoke-RestMethod -Uri "$api/benchmark/runs" -Headers $auth
Invoke-RestMethod -Uri "$api/benchmark/runs/<run-id>" -Headers $auth | ConvertTo-Json -Depth 8

# 5. The analysed complaints as a report (JSON, filtered by tag)
Invoke-RestMethod -Uri "$api/analytics/reports/COMPLAINTS?dataset_tag=HIDDEN-PACK" -Headers $auth | ConvertTo-Json -Depth 6
```

| Endpoint | Who | What it does |
|---|---|---|
| `POST /api/benchmark/datasets/{tag}/import` | Evaluator, Administrator | Multipart field `file`; `?replace=true` clears the tag first. Stores rows only. |
| `GET /api/benchmark/datasets` and `/datasets/{tag}` | Evaluator, Administrator, Manager | Counts per tag: total, labelled, unlabelled, analysed, pending. |
| `POST /api/benchmark/run` | Evaluator, Administrator | `dataset_tag` (required), `label`, `limit` (1 to 2000), `run_genai` (default true), `workers` (1 to 16, default 4), `resume` (default true). |
| `GET /api/benchmark/runs`, `/runs/{id}` | Evaluator, Administrator, Manager | Run list with ruleset, prompt, provider and model; one run with metrics and rule failures. |
| `DELETE /api/benchmark/datasets/{tag}` | Administrator | Removes every complaint under the tag. Irreversible. |

All endpoints are also documented, and can be tried, at `/api/docs`.

## Good to know

* The run is processed inside the HTTP request. Keep GenAI batches small (25 to 50) on the free tier; a
  rules-only run of 500 complaints is fine in one call.
* A complaint analysed while every AI provider was unavailable is stored as a rules-only (degraded) result and is
  counted as analysed. Its verification says the AI was unavailable, GenAI accuracy leaves it out of the
  denominator, and pipeline-agreement figures exclude it.
* Imported complaints are numbered in the same `CMP-000000` sequence as submitted ones and show up in the
  dashboards and analytics. An administrator can remove them afterwards with the `DELETE` endpoint above
  (**Delete dataset** on the dataset page).
* Unseen policy documents are also handled without code changes: upload them as an administrator
  (**Policy Versions**). A document with missing metadata is kept in *metadata review* rather than rejected.
