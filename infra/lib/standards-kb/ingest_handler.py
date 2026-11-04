# Standards KB ingestion custom resource (#17). Inlined into the Lambda (no CDK assets): keep under 4 KB.
# CloudFormation event: start the ingestion job and a Step Functions poll loop, then return without
# answering; the loop calls back here until the job ends and answers CloudFormation. Delete: no-op.
import json
import os
import time
import urllib.request

import boto3

kb = boto3.client("bedrock-agent")
sfn = boto3.client("stepfunctions")


def respond(cfn, ok, reason="", data=None):
    body = json.dumps({
        "Status": "SUCCESS" if ok else "FAILED", "Reason": (reason or "ok")[:900],
        "PhysicalResourceId": cfn["PhysicalResourceId"], "StackId": cfn["StackId"],
        "RequestId": cfn["RequestId"], "LogicalResourceId": cfn["LogicalResourceId"], "Data": data or {},
    }).encode()
    req = urllib.request.Request(cfn["ResponseURL"], data=body, method="PUT", headers={"Content-Type": ""})
    urllib.request.urlopen(req, timeout=30)


def start(event):
    p = event["ResourceProperties"]
    cfn = {k: event[k] for k in ("ResponseURL", "StackId", "RequestId", "LogicalResourceId")}
    cfn["PhysicalResourceId"] = event.get("PhysicalResourceId") or f"{p['KnowledgeBaseId']}/{p['DataSourceId']}"
    if event["RequestType"] == "Delete":
        return respond(cfn, True, "nothing to do on delete")
    try:
        job = kb.start_ingestion_job(knowledgeBaseId=p["KnowledgeBaseId"], dataSourceId=p["DataSourceId"])
        state = {"cfn": cfn, "kb": p["KnowledgeBaseId"], "ds": p["DataSourceId"],
                 "job": job["ingestionJob"]["ingestionJobId"],
                 "deadline": time.time() + int(os.environ["LIMIT_SECONDS"]), "done": False}
        sfn.start_execution(stateMachineArn=os.environ["STATE_MACHINE_ARN"], input=json.dumps(state))
    except Exception as exc:  # noqa: BLE001 - reported to CloudFormation
        respond(cfn, False, f"could not start ingestion: {exc}")


def poll(state):
    cfn = state["cfn"]
    if "error" in state:  # the state machine caught a failure in a poll
        respond(cfn, False, "ingestion poll failed: " + json.dumps(state["error"])[:600])
        return {**state, "done": True}
    job = kb.get_ingestion_job(knowledgeBaseId=state["kb"], dataSourceId=state["ds"],
                               ingestionJobId=state["job"])["ingestionJob"]
    status, stats = job["status"], job.get("statistics", {})
    if status == "COMPLETE":
        failed = stats.get("numberOfDocumentsFailed", 0)
        respond(cfn, not failed, f"{failed} documents failed" if failed else "ingested",
                {"IngestionJobId": state["job"], "Documents": str(stats.get("numberOfNewDocumentsIndexed", 0)
                                                                    + stats.get("numberOfModifiedDocumentsIndexed", 0))})
    elif status in ("FAILED", "STOPPED"):
        respond(cfn, False, f"ingestion {status}: " + "; ".join(job.get("failureReasons", []))[:700])
    elif time.time() > state["deadline"]:
        try:
            kb.stop_ingestion_job(knowledgeBaseId=state["kb"], dataSourceId=state["ds"], ingestionJobId=state["job"])
        finally:
            respond(cfn, False, "ingestion did not finish within the time limit")
    else:
        return {**state, "done": False}
    return {**state, "done": True}


def handler(event, _context):
    return start(event) if "RequestType" in event else poll(event)
