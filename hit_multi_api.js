const https = require("https");
const fs = require("fs");

// ─── CONFIGURATION ───────────────────────────────────────────
const TOKEN ="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IldJcXJlYVZTR1EtMWhLXzNzemRVVCJ9.eyJvcmciOnsiZGlzcGxheV9uYW1lIjoiRmFjY3R2aWV3IiwiaWQiOiJvcmdfSFh3SE51M0w3RmVHbXVXYSIsIm1ldGFkYXRhIjp7ImNyZWF0aW9uX3RpbWVzdGFtcCI6IkZyaSBBcHIgMDUgMjAyNCAxMDozNDoxMiBHTVQrMDAwMCAoQ29vcmRpbmF0ZWQgVW5pdmVyc2FsIFRpbWUpIiwiY3JlYXRvcl9lbWFpbCI6ImFkbWluQGNhcC5jb20ifSwibmFtZSI6ImZhY2N0dmlldyJ9LCJ0ZW5hbnRJZCI6ImZhY2N0dmlldyIsImdlb2lwIjp7ImNpdHlOYW1lIjoiUHVuZSIsImNvbnRpbmVudENvZGUiOiJBUyIsImNvdW50cnlDb2RlIjoiSU4iLCJjb3VudHJ5Q29kZTMiOiJJTkQiLCJjb3VudHJ5TmFtZSI6IkluZGlhIiwibGF0aXR1ZGUiOjE4LjUyMTEsImxvbmdpdHVkZSI6NzMuODUwMiwic3ViZGl2aXNpb25Db2RlIjoiTUgiLCJzdWJkaXZpc2lvbk5hbWUiOiJNYWhhcmFzaHRyYSIsInRpbWVab25lIjoiQXNpYS9Lb2xrYXRhIn0sInVzZXJJbmZvIjp7ImFwcF9tZXRhZGF0YSI6e30sImNyZWF0ZWRfYXQiOiIyMDI0LTA0LTE2VDExOjU2OjExLjQ5NFoiLCJlbWFpbCI6ImFkbWluQGZhY2N0dmlldy5jb20iLCJlbWFpbF92ZXJpZmllZCI6ZmFsc2UsImlkZW50aXRpZXMiOlt7ImNvbm5lY3Rpb24iOiJVc2VybmFtZS1QYXNzd29yZC1BdXRoZW50aWNhdGlvbiIsImlzU29jaWFsIjpmYWxzZSwicHJvdmlkZXIiOiJhdXRoMCIsInVzZXJJZCI6IjY2MWU2NzViNGIwMzNmZmRmZTM0NjA2YSIsInVzZXJfaWQiOiI2NjFlNjc1YjRiMDMzZmZkZmUzNDYwNmEifV0sImxhc3RfcGFzc3dvcmRfcmVzZXQiOiIyMDI0LTA0LTE2VDExOjU2OjQ1LjcyOFoiLCJtdWx0aWZhY3RvciI6W10sIm5hbWUiOiJBZG1pbiIsIm5pY2tuYW1lIjoiYWRtaW4iLCJwaWN0dXJlIjoiaHR0cHM6Ly9zZWN1cmUuZ3JhdmF0YXIuY29tL2F2YXRhci8xNTYyNmM1ZTBjNzQ5Y2I5MTJmOWQxYWQ0OGRiYTQ0MD9zPTQ4MCZyPXBnJmQ9aHR0cHMlM0ElMkYlMkZzc2wuZ3N0YXRpYy5jb20lMkZzMiUyRnByb2ZpbGVzJTJGaW1hZ2VzJTJGc2lsaG91ZXR0ZTgwLnBuZyIsInVwZGF0ZWRfYXQiOiIyMDI2LTA0LTI4VDA3OjAwOjExLjYwMVoiLCJ1c2VyX2lkIjoiYXV0aDB8NjYxZTY3NWI0YjAzM2ZmZGZlMzQ2MDZhIiwidXNlcl9tZXRhZGF0YSI6e319LCJyb3V0ZSI6IlVJIiwiaXNzIjoiaHR0cHM6Ly9hdXRoLXFhLXNhYXMuZmFjY3R1bS5jb20vIiwic3ViIjoiYXV0aDB8NjYxZTY3NWI0YjAzM2ZmZGZlMzQ2MDZhIiwiYXVkIjpbImh0dHBzOi8vcWEtc2Fhcy5mYWNjdHVtLmNvbSIsImh0dHBzOi8vZmFjY3R1bS1xdWFsaXR5LWFzc3VyYW5jZS5ldS5hdXRoMC5jb20vdXNlcmluZm8iXSwiaWF0IjoxNzc3MzU5NjQzLCJleHAiOjE3NzczNjA1NDMsInNjb3BlIjoib3BlbmlkIHByb2ZpbGUgZW1haWwgb2ZmbGluZV9hY2Nlc3MiLCJvcmdfaWQiOiJvcmdfSFh3SE51M0w3RmVHbXVXYSIsImF6cCI6IjVnMHBNMEkxclhsUmhaeDFqeDdYZWNHWWNuRUpxZ05pIn0.gJ5bfDo_IMD5mAgw_rIhEF9H8kzcl4mzCs8UGhDK9jxN3kucybZPMcMlCB_ZwLmt-orBT7cj_u8mAy1ebejbxmbjZ-tAHusunY-FHK1IurF08ZeA6cueupFmAQd60gC4ZQbyChp5N1lQTxICc8CDPLL1cmK7FUladFZK_qbirco8DeSsAC4mt3nWBE5ui08q0GacD1URdNSEpuS_xDmWGeSMWaXJEF4ygpgk01IjMtCHyFYWVWGyyRtOgZ4rL6-KKJG9kyJsK1tC4flPmDy-5ZM5-0zAXltiTbtUOZpWu1Dfy8VTya9utd4kmhTMOQQ3uD036MGPKDG-Ip8dF5lERw";

const EXTRA_HEADERS = {
  "Accept": "application/json, text/plain, */*",
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
  "Referer": "https://qa-saas.facctum.com/facctlist/watchlist/internal-list/64?listStatus=approved",
  "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
  "sec-ch-ua-mobile": "?0",
  "sec-ch-ua-platform": '"Windows"',
};

const DURATION_MS = 110000; // 110 seconds

// Add/remove APIs here. Each entry: { name, url, method, hits }
const APIS = [
  {
    name: "IL profile view",
    url: "https://qa-saas.facctum.com/facctlist/api/v2/ilList/blockList/records?wf_status_id=1&limit=10&offset=0&sort_by=listEntryId&sort_order=1&wf_status_ids=99%2C1%2C100%2C101%2C200%2C201%2C2005&blocklist_id=64",
    method: "GET",
    hits: 300,
  },
  {
    name: "IBL Rejected Tab API",
    url: "https://qa-saas.facctum.com/facctlist/api/v2/ilList/blockList/records?wf_status_id=0&limit=10&offset=0&sort_by=listEntryId&sort_order=1&blocklist_id=64",
    method: "GET",
    hits: 200,
  },
  {
    name: "IBL deleted Tab API",
    url: "https://qa-saas.facctum.com/facctlist/api/v2/ilList/blockList/records?wf_status_id=2005&blocklist_id=71",
    method: "GET",
    hits: 300,
  },
//   {
//     name: "IBL Advance Filter API",
//     url: "https://qa-saas.facctum.com/facctlist/api/v2/ilList/blockList/records/filter",
//     method: "POST",
//     hits: 50,
//     body: JSON.stringify({
//       page_size: 10,
//       page_number: 0,
//       filters: [{ attribute_name: "actionId", data_type: "multi_drop_down", filter_order: 4, label: "Action", value: [1, 2] }],
//       sort_order: 1,
//       sort_by: "listEntryId",
//       blocklist_id: "64",
//       wf_status_id: 1,
//     }),
//   },
//   {
//     name: "IBL Records Download API",
//     url: "https://qa-saas.facctum.com/facctlist/api/v2/recordsDownload/all?limit=10&list_id=64&list_type_id=3",
//     method: "GET",
//     hits: 200,
//   },
  {
    name: "Record view",
    url: "https://qa-saas.facctum.com/facctlist/api/v2/ilList/blockList/records?wf_status_id=1&limit=10&offset=0&sort_by=listEntryId&sort_order=1&wf_status_ids=99%2C1%2C100%2C101%2C200%2C201%2C2005&blocklist_id=64",
    method: "GET",
    hits: 300,
  },
];

// ─── TRACKING ────────────────────────────────────────────────
const stats = {};
const allResponses = [];
let totalRequests = 0;
let totalCompleted = 0;

APIS.forEach((api) => {
  totalRequests += api.hits;
  stats[api.name] = { success: 0, fail: 0, completed: 0, total: api.hits };
});

// ─── REQUEST LOGIC ───────────────────────────────────────────
function fireRequest(api, index) {
  const parsed = new URL(api.url);
  const headers = { Authorization: `Bearer ${TOKEN}`, ...EXTRA_HEADERS };
  if (api.body) {
    headers["Content-Type"] = "application/json";
    headers["Content-Length"] = Buffer.byteLength(api.body);
  }

  const options = {
    hostname: parsed.hostname,
    path: parsed.pathname + parsed.search,
    method: api.method,
    headers,
  };

  const req = https.request(options, (res) => {
    let body = "";
    res.on("data", (chunk) => (body += chunk));
    res.on("end", () => {
      let jsonBody;
      try {
        jsonBody = JSON.parse(body);
      } catch {
        jsonBody = body;
      }

      const count = jsonBody?.data?.count || "N/A";

      allResponses.push({
        api: api.name,
        request: index,
        status: res.statusCode,
        count,
      });

      if (res.statusCode === 200) {
        stats[api.name].success++;
        console.log(`[${api.name}] #${index} - 200 ✓ | Count: ${JSON.stringify(count)}`);
      } else {
        stats[api.name].fail++;
        console.log(`[${api.name}] #${index} - ${res.statusCode} ✗`);
      }
      onComplete();
    });
  });

  req.on("error", (err) => {
    stats[api.name].fail++;
    allResponses.push({ api: api.name, request: index, status: "ERROR", response: err.message });
    console.log(`[${api.name}] #${index} - Error: ${err.message}`);
    onComplete();
  });

  if (api.body) {
    req.write(api.body);
  }
  req.end();
}

// ─── COMPLETION & SUMMARY ────────────────────────────────────
function onComplete() {
  totalCompleted++;
  if (totalCompleted === totalRequests) {
    const elapsedSec = (Date.now() - startTime) / 1000;
    const tps = (totalRequests / elapsedSec).toFixed(2);

    console.log("\n" + "=".repeat(60));
    console.log("SUMMARY");
    console.log("=".repeat(60));
    console.log(`Total Time : ${elapsedSec.toFixed(1)}s`);
    console.log(`Total Reqs : ${totalRequests}`);
    console.log(`Overall TPS: ${tps}\n`);

    for (const api of APIS) {
      const s = stats[api.name];
      const apiTps = (s.total / elapsedSec).toFixed(2);
      console.log(`  [${api.name}] ${s.success} ok / ${s.fail} fail (${s.total} total) — TPS: ${apiTps}`);
    }

    // Save results
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const outputFile = `multi_api_responses_${timestamp}.json`;
    fs.writeFileSync(outputFile, JSON.stringify(allResponses, null, 2));
    console.log(`\nAll responses saved to ${outputFile}`);
  }
}

// ─── LAUNCH ──────────────────────────────────────────────────
console.log(`Launching ${totalRequests} total requests across ${APIS.length} APIs over 60s\n`);
APIS.forEach((api) => {
  const interval = DURATION_MS / api.hits;
  console.log(`  [${api.name}] ${api.hits} hits (~1 every ${interval.toFixed(0)}ms)`);
});
console.log("=".repeat(60));

const startTime = Date.now();

APIS.forEach((api) => {
  const interval = DURATION_MS / api.hits;
  for (let i = 1; i <= api.hits; i++) {
    setTimeout(() => fireRequest(api, i), (i - 1) * interval);
  }
});
