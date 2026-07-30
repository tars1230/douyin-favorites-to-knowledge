import os
import unittest
from unittest.mock import Mock, patch

from douyin_favorites_knowledge import douyin_mcp


class DouyinMcpTests(unittest.TestCase):
    def test_extracts_nested_mcp_text(self):
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}, clear=True), patch(
            "douyin_favorites_knowledge.douyin_mcp.shutil.which", return_value="/usr/bin/mcporter"
        ), patch("douyin_favorites_knowledge.douyin_mcp.subprocess.run") as run:
            run.side_effect = [
                Mock(returncode=0, stdout="douyin-mcp", stderr=""),
                Mock(returncode=0, stdout='{"command":"uvx douyin-mcp-server@1.2.1"}', stderr=""),
                Mock(returncode=0, stdout='{"result": {"content": "完整语音文本"}}', stderr=""),
            ]
            result = douyin_mcp.transcribe({"source_url": "https://www.douyin.com/video/7000000000000000001"}, {})
        self.assertEqual(result["transcript"], "完整语音文本")
        self.assertEqual(result["transcript_source"], "douyin_mcp")
        self.assertEqual(result["transcript_status"], "success")

    def test_missing_key_is_reported_without_secret(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "douyin_favorites_knowledge.douyin_mcp.shutil.which", return_value="/usr/bin/mcporter"
        ), patch("douyin_favorites_knowledge.douyin_mcp.subprocess.run"):
            result = douyin_mcp.check_environment()
        self.assertEqual(result, {"ready": False, "missing": ["DASHSCOPE_API_KEY"]})

    def test_legacy_mcp_server_is_rejected(self):
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}, clear=True), patch(
            "douyin_favorites_knowledge.douyin_mcp.shutil.which", return_value="/usr/bin/mcporter"
        ), patch("douyin_favorites_knowledge.douyin_mcp.subprocess.run") as run:
            run.side_effect = [
                Mock(returncode=0, stdout="douyin-mcp", stderr=""),
                Mock(returncode=0, stdout='{"command":"uvx douyin-mcp-server@1.1.0"}', stderr=""),
            ]
            result = douyin_mcp.check_environment()
        self.assertEqual(result, {"ready": False, "missing": ["douyin-mcp-server>=1.2.1"]})
