const https = require("https");
const fs = require("fs");

const API_URL =
  "https://api-qa-saas.facctum.com/facctlist/v1/blocklist/records?blocklist_id=64";

const TOKEN =
  "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IldJcXJlYVZTR1EtMWhLXzNzemRVVCJ9.eyJnZW9pcCI6eyJjaXR5TmFtZSI6IkJlbmdhbHVydSIsImNvbnRpbmVudENvZGUiOiJBUyIsImNvdW50cnlDb2RlIjoiSU4iLCJjb3VudHJ5Q29kZTMiOiJJTkQiLCJjb3VudHJ5TmFtZSI6IkluZGlhIiwibGF0aXR1ZGUiOjEyLjk3NTMsImxvbmdpdHVkZSI6NzcuNTkxLCJzdWJkaXZpc2lvbkNvZGUiOiJLQSIsInN1YmRpdmlzaW9uTmFtZSI6Ikthcm5hdGFrYSIsInRpbWVab25lIjoiQXNpYS9Lb2xrYXRhIn0sIm9yZyI6eyJkaXNwbGF5X25hbWUiOiJGYWNjdHVtIHNvbHV0aW9ucyIsImlkIjoib3JnX2N3eUF2QlpITlVxa0RMbWMiLCJtZXRhZGF0YSI6eyJjcmVhdGlvbl90aW1lc3RhbXAiOiJUaHUgQXByIDA0IDIwMjQgMDg6Mjg6MDMgR01UKzAwMDAgKENvb3JkaW5hdGVkIFVuaXZlcnNhbCBUaW1lKSIsImNyZWF0b3JfZW1haWwiOiJhZG1pbkBjYXAuY29tIn0sIm5hbWUiOiJmYWNjdHVtIn0sInRlbmFudElkIjoiZmFjY3R1bSIsInJvdXRlIjoiQVBJIiwiaXNzIjoiaHR0cHM6Ly9hdXRoLXFhLXNhYXMuZmFjY3R1bS5jb20vIiwic3ViIjoiYzczaDBxQnpoQ1RJTklxWURLNkFHMDI1ZnREbUhaVFNAY2xpZW50cyIsImF1ZCI6Imh0dHBzOi8vYXBpLXFhLXNhYXMuZmFjY3R1bS5jb20iLCJpYXQiOjE3Nzc0Mzk5MzMsImV4cCI6MTc3NzUyNjMzMywiZ3R5IjoiY2xpZW50LWNyZWRlbnRpYWxzIiwiYXpwIjoiYzczaDBxQnpoQ1RJTklxWURLNkFHMDI1ZnREbUhaVFMiLCJwZXJtaXNzaW9ucyI6W119.C2cMs0YNIgExzb_M0ZCNZdxyW4rghBoP5CtRWvnl7b-_azsL2_MyF_gADHwmpuP-JaHFftxY-M4s8Vgfg9aRcwzAHiNTvhT2yah0lxcd6PSo3zCHRd8ISyPVOpPV-iGpvbBhcgL8q0suocjdSpHDRli0QOVe3F8aZ4F-U-D9MD3w91PZIii_dSuzzRme5J_Hxh48xy6609OVuzNbhWbO87lJBK6rPQRe39QQWhp5zZCuN_bZQiVdFL__amtckVcZBBzNKzQBaehnHF5FZbWBjauN6d1y8ONZDSyZaz0SJH36lLWlCs2gxlYM3UiizcIufUUnoYcI2yxvleB49FCB3Q";

const TOTAL = 600;
const DURATION_MS = 60000;
const INTERVAL_MS = DURATION_MS / TOTAL; // 600ms between requests

let success = 0;
let fail = 0;
let completed = 0;
const allResponses = [];

function fireRequest(index) {
  const parsed = new URL(API_URL);
  const options = {
    hostname: parsed.hostname,
    path: parsed.pathname + parsed.search,
    method: "GET",
    headers: { Authorization: `Bearer ${TOKEN}` },
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

      allResponses.push({
        request: index,
        status: res.statusCode,
        response: jsonBody,
      });

      if (res.statusCode === 200) {
        success++;
        const count = jsonBody?.data?.count || "N/A";
        console.log(`Request #${index} - Status: ${res.statusCode} ✓ | Count: ${JSON.stringify(count)}`);
      } else {
        fail++;
        console.log(`Request #${index} - Status: ${res.statusCode} ✗ | ${JSON.stringify(jsonBody).substring(0, 200)}`);
      }
      checkDone();
    });
  });

  req.on("error", (err) => {
    fail++;
    allResponses.push({ request: index, status: "ERROR", response: err.message });
    console.log(`Request #${index} - Error: ${err.message}`);
    checkDone();
  });

  req.end();
}

function checkDone() {
  completed++;
  if (completed === TOTAL) {
    const elapsedSec = (Date.now() - startTime) / 1000;
    const tps = (TOTAL / elapsedSec).toFixed(2);
    console.log("=".repeat(55));
    console.log(`Done in ${elapsedSec.toFixed(1)}s | Success: ${success} | Failed: ${fail}`);
    console.log(`TPS (Transactions Per Second): ${tps}`);

    // Save all responses to a timestamped JSON file
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const outputFile = `api_responses_${timestamp}.json`;
    fs.writeFileSync(outputFile, JSON.stringify(allResponses, null, 2));
    console.log(`All responses saved to ${outputFile}`);
  }
}

console.log(`Firing ${TOTAL} requests spread over 60 seconds (~1 every ${INTERVAL_MS}ms)`);
console.log("=".repeat(55));

const startTime = Date.now();

for (let i = 1; i <= TOTAL; i++) {
  setTimeout(() => fireRequest(i), (i - 1) * INTERVAL_MS);
}
