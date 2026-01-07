"""
Metrics Tool - Get Jenkins build metrics for FXOS/ASA pipelines.

This tool retrieves build metrics from Jenkins including:
- Build duration per platform
- Bazel cache hit statistics
- Cache hit percentage

Platforms:
- FXOS: arm, armv, ssp, smp, arsenal, wpk, fp1k, fp3k, fp4k
- ASA: arm, arm8, smp, ssp
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


class MetricsTool:
    """MCP Tool for retrieving Jenkins build metrics."""
    
    description = "Get Jenkins build metrics for FXOS or ASA pipelines"
    
    parameters = {
        "job_type": {
            "type": "string",
            "description": "Pipeline type: FXOS or ASA",
            "enum": ["FXOS", "ASA"]
        },
        "build_number": {
            "type": "integer",
            "description": "Specific build number (optional, defaults to latest)"
        }
    }
    
    required_params = ["job_type"]
    
    # Platform configurations
    FXOS_PLATFORMS = [
        {"id": "arm", "dir": "ARMsa/image", "outfile": "ARM-OutFile.txt", "cache": "bazel_cache.txt"},
        {"id": "armv", "dir": "ARMVsa/image", "outfile": "ARMV-OutFile.txt", "cache": "bazel_cache.txt"},
        {"id": "ssp", "dir": "sspsa/image", "outfile": "ssp-OutFile.txt", "cache": "bazel_cache.txt"},
        {"id": "smp", "dir": "smpsa/image", "outfile": "smp-OutFile.txt", "cache": "bazel_cache.txt"},
        {"id": "arsenal", "dir": "ARSENALsa/image", "outfile": "ARSENAL-OutFile.txt", "cache": "bazel_cache.txt"},
        {"id": "wpk", "dir": "WPKsa/image", "outfile": "WPK-OutFile.txt", "cache": "bazel_cache.txt"},
        {"id": "fp1k", "dir": "FP1Ksa/image", "outfile": "FP1K-OutFile.txt", "cache": "bazel_cache.txt"},
        {"id": "fp3k", "dir": "FP3Ksa/image", "outfile": "FP3K-OutFile.txt", "cache": "bazel_cache.txt"},
        {"id": "fp4k", "dir": "FP4Ksa/image", "outfile": "FP4K-OutFile.txt", "cache": "bazel_cache.txt"},
    ]
    
    ASA_PLATFORMS = [
        {"id": "arm", "dir": "ARMsa/Xpix", "outfile": "armOut.txt"},
        {"id": "arm8", "dir": "ARMv8sa/Xpix", "outfile": "armv8Out.txt"},
        {"id": "smp", "dir": "SMPsa/Xpix", "outfile": "smpOut.txt"},
        {"id": "ssp", "dir": "SSPsa/Xpix", "outfile": "sspOut.txt"},
    ]
    
    # Regex patterns
    BUILD_START_RE = re.compile(r"BUILD_TIME_START\s*:\s*(.+)")
    BUILD_END_RE = re.compile(r"BUILD_TIME_END\s*:\s*(.+)")
    
    def __init__(self):
        self.jenkins_base = os.getenv("JENKINS_BASE_URL", "")
        self.jenkins_user = os.getenv("JENKINS_USER", "")
        self.jenkins_token = os.getenv("JENKINS_API_TOKEN", "")
        self.job_path_fxos = os.getenv("JENKINS_JOB_PATH_FXOS_PB", "")
        self.job_path_asa = os.getenv("JENKINS_JOB_PATH_ASA", "")
        
        self._session = None
    
    @property
    def session(self) -> requests.Session:
        """Get authenticated requests session."""
        if self._session is None:
            self._session = requests.Session()
            self._session.auth = (self.jenkins_user, self.jenkins_token)
            self._session.headers.update({"Accept": "application/json"})
        return self._session
    
    def execute(self, job_type: str, build_number: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute the metrics tool.
        
        Args:
            job_type: FXOS or ASA
            build_number: Optional specific build number
            
        Returns:
            Dict with metrics data and formatted output
        """
        job_type = job_type.upper()
        
        if job_type == "FXOS":
            job_path = self.job_path_fxos
            platforms = self.FXOS_PLATFORMS
        elif job_type == "ASA":
            job_path = self.job_path_asa
            platforms = self.ASA_PLATFORMS
        else:
            return {"error": f"Invalid job_type: {job_type}"}
        
        # Get build number if not specified
        if build_number is None:
            build_alias, build_number = self._get_latest_build(job_path)
            if build_number is None:
                return {"error": f"Could not determine build number: {build_alias}"}
        
        # Collect metrics for each platform
        rows = []
        for platform in platforms:
            row = self._collect_platform_metrics(job_path, build_number, platform, job_type)
            rows.append(row)
        
        # Format output
        formatted = self._format_metrics(rows, job_type, build_number, job_path)
        
        return {
            "job_type": job_type,
            "build_number": build_number,
            "rows": rows,
            "formatted_output": formatted
        }
    
    def _get_latest_build(self, job_path: str) -> Tuple[str, Optional[int]]:
        """Get the latest build number for a job."""
        api_url = f"{self.jenkins_base.rstrip('/')}/{job_path.strip('/')}/api/json"
        
        try:
            r = self.session.get(api_url, timeout=15)
            if r.status_code != 200:
                return f"Job API returned {r.status_code}", None
            
            data = r.json()
            if data.get("lastBuild"):
                return "lastBuild", data["lastBuild"].get("number")
            return "No builds found", None
        
        except requests.RequestException as e:
            return str(e), None
    
    def _collect_platform_metrics(
        self,
        job_path: str,
        build_number: int,
        platform: Dict[str, str],
        job_type: str
    ) -> Dict[str, Any]:
        """Collect metrics for a single platform."""
        plat_id = platform["id"]
        plat_dir = platform["dir"]
        outfile = platform["outfile"]
        cache_file = platform.get("cache")
        
        result = {
            "platform": plat_id,
            "duration_mmss": None,
            "cache_hit": None,
            "cache_total": None,
            "cache_pct": None,
            "errors": []
        }
        
        # Build artifact URL
        artifact_root = f"{self.jenkins_base.rstrip('/')}/{job_path.strip('/')}/{build_number}/artifact"
        outfile_url = f"{artifact_root}/{plat_dir}/{outfile}"
        
        # Fetch outfile for build times
        try:
            r = self.session.get(outfile_url, timeout=20)
            if r.status_code == 200:
                start, end = self._parse_build_times(r.text)
                if start and end:
                    duration = self._calculate_duration(start, end)
                    if duration:
                        result["duration_mmss"] = self._format_duration(duration)
                
                # For ASA, parse cache from outfile (process info)
                if job_type == "ASA":
                    hit, total = self._parse_asa_cache(r.text)
                    if hit is not None and total is not None:
                        result["cache_hit"] = hit
                        result["cache_total"] = total
                        result["cache_pct"] = (hit / total * 100) if total > 0 else 0
            else:
                result["errors"].append(f"Outfile: HTTP {r.status_code}")
        except requests.RequestException as e:
            result["errors"].append(f"Outfile: {e}")
        
        # Fetch cache file for FXOS
        if cache_file and job_type == "FXOS":
            cache_url = f"{artifact_root}/{plat_dir}/{cache_file}"
            try:
                r = self.session.get(cache_url, timeout=20)
                if r.status_code == 200:
                    hit, total = self._parse_cache_file(r.text)
                    if hit is not None:
                        result["cache_hit"] = hit
                        result["cache_total"] = total
                        result["cache_pct"] = (hit / total * 100) if total > 0 else 0
                else:
                    result["errors"].append(f"Cache: HTTP {r.status_code}")
            except requests.RequestException as e:
                result["errors"].append(f"Cache: {e}")
        
        return result
    
    def _parse_build_times(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse build start and end times from outfile."""
        start_match = self.BUILD_START_RE.search(text)
        end_match = self.BUILD_END_RE.search(text)
        
        start = start_match.group(1).strip() if start_match else None
        end = end_match.group(1).strip() if end_match else None
        
        return start, end
    
    def _calculate_duration(self, start: str, end: str) -> Optional[float]:
        """Calculate duration in seconds between timestamps."""
        start_ts = self._parse_timestamp(start)
        end_ts = self._parse_timestamp(end)
        
        if start_ts and end_ts:
            return end_ts - start_ts
        return None
    
    def _parse_timestamp(self, raw: str) -> Optional[float]:
        """Parse timestamp string to epoch."""
        if not raw:
            return None
        
        # Example: Tue Nov 25 05:21:30 UTC 2025
        formats = [
            "%a %b %d %H:%M:%S %Z %Y",
            "%a %b %e %H:%M:%S %Z %Y",
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.timestamp()
            except ValueError:
                continue
        
        return None
    
    def _format_duration(self, seconds: float) -> str:
        """Format seconds as MM:SS."""
        total = int(round(seconds))
        m = total // 60
        s = total % 60
        return f"{m:02d}:{s:02d}"
    
    def _parse_cache_file(self, text: str) -> Tuple[Optional[int], Optional[int]]:
        """Parse FXOS bazel_cache.txt for hit stats."""
        # Look for: remote cache hit: 12345 / 15000
        match = re.search(r"remote cache hit:\s*(\d+)\s*/\s*(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None, None
    
    def _parse_asa_cache(self, text: str) -> Tuple[Optional[int], Optional[int]]:
        """Parse ASA outfile for cache stats from process info."""
        # Find second "Elapsed time" block and get process info
        elapsed_pattern = re.compile(r"INFO:\s*Elapsed time:\s*([\d.]+)s", re.IGNORECASE)
        elapsed_matches = list(elapsed_pattern.finditer(text))
        
        if len(elapsed_matches) < 2:
            return None, None
        
        remaining = text[elapsed_matches[1].end():]
        
        # Pattern: INFO: 15030 processes: 14875 remote cache hit
        process_match = re.search(
            r"INFO:\s*(\d+)\s+processes:\s*(\d+)\s+remote cache hit",
            remaining,
            re.IGNORECASE
        )
        
        if process_match:
            total = int(process_match.group(1))
            hit = int(process_match.group(2))
            return hit, total
        
        return None, None
    
    def _format_metrics(
        self,
        rows: List[Dict[str, Any]],
        job_type: str,
        build_number: int,
        job_path: str
    ) -> str:
        """Format metrics as fixed-width text block for Webex."""
        if not rows:
            return "🔧 Jenkins Build Metrics\nNo data available"
        
        total_platforms = len(rows)
        issues = sum(1 for r in rows if r.get("errors"))
        
        lines = [
            f"🔧 **Jenkins Build Metrics - {job_type}**",
            f"Build #{build_number} | Platforms: {total_platforms} | Issues: {issues}",
            "",
            "```",
            f"{'Platform':<10} {'Build Time':>12} {'Cache Hit %':>12} {'Hits / Total':>15} {'Status':<15}",
            "-" * 70,
        ]
        
        for row in rows:
            plat = row.get("platform", "-").upper()
            dur = row.get("duration_mmss") or "—"
            hit = row.get("cache_hit")
            tot = row.get("cache_total")
            pct = row.get("cache_pct")
            errs = row.get("errors", [])
            
            pct_str = f"{pct:.1f}%" if isinstance(pct, (int, float)) else "—"
            ratio = f"{hit:,} / {tot:,}" if hit is not None and tot is not None else "—"
            status = f"⚠️ {errs[0][:20]}" if errs else "✅ OK"
            
            lines.append(f"{plat:<10} {dur:>12} {pct_str:>12} {ratio:>15} {status:<15}")
        
        lines.extend([
            "```",
            "",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}*"
        ])
        
        return "\n".join(lines)
