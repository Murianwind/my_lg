"""Write a pass/fail markdown summary of a pytest JUnit XML report to
GitHub Actions' step summary file ($GITHUB_STEP_SUMMARY).

Usage: python write_test_summary.py <junit-xml-path> <label>
"""

import os
import sys
import xml.etree.ElementTree as ET

junit_path, label = sys.argv[1], sys.argv[2]

tree = ET.parse(junit_path)
suite = tree.getroot().find("testsuite")
tests = int(suite.get("tests", 0))
failures = int(suite.get("failures", 0))
errors = int(suite.get("errors", 0))
skipped = int(suite.get("skipped", 0))
passed = tests - failures - errors - skipped
status = "✅ 통과" if failures == 0 and errors == 0 else "❌ 실패"

lines = [
    f"### 테스트 결과 ({label}): {status}",
    "",
    "| 전체 | 통과 | 실패 | 오류 | 스킵 | 소요 시간 |",
    "|---|---|---|---|---|---|",
    f"| {tests} | {passed} | {failures} | {errors} | {skipped} | {suite.get('time')}s |",
]

failed_cases = [
    case
    for case in suite.findall("testcase")
    if case.find("failure") is not None or case.find("error") is not None
]
if failed_cases:
    lines += ["", "#### 실패한 시나리오", ""]
    for case in failed_cases:
        lines.append(f"- `{case.get('classname')}::{case.get('name')}`")

with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
