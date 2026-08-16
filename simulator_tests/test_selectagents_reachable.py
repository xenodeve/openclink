#!/usr/bin/env python3
"""
SelectAgents Reachability Test

The end-to-end leg `docs/adding_tools.md` requires and #99 restates: a tool that
passes unit tests has been shown to work, not to be *reachable*. This drives the
real server over MCP — initialize, list tools, call by name — so a registration
that exists only in an import would fail here.

Deliberately checks nothing about the answer. Until #104 there is no ranking
behind `selectagents`, so the only honest assertion is that the path exists and
that the stub says it is a stub.
"""

from .base_test import BaseSimulatorTest


class SelectAgentsReachableTest(BaseSimulatorTest):
    """Prove the selection tool is advertised and dispatched by the real server"""

    @property
    def test_name(self) -> str:
        return "selectagents_reachable"

    @property
    def test_description(self) -> str:
        return "SelectAgents tool reachability through the server"

    def run_test(self) -> bool:
        try:
            self.logger.info("📋 Test: selectagents is advertised and callable through the server")

            response, _continuation_id = self.call_mcp_tool("selectagents", {})
            if not response:
                self.logger.error("❌ selectagents returned nothing — the tool is not reachable")
                return False

            # The stub must announce itself. A placeholder that reads like a real
            # plan is the failure #96 exists to prevent, one layer earlier: a
            # caller would act on a delegation nobody computed.
            if "not implemented" not in response.lower():
                self.logger.error(
                    "❌ selectagents answered without declaring itself a stub — "
                    "a caller could mistake this for a computed plan"
                )
                self.logger.error(f"   response: {response[:300]}")
                return False

            self.logger.info("✅ selectagents is reachable and honest about being a stub")
            return True

        except Exception as e:
            self.logger.error(f"❌ selectagents reachability test failed: {e}")
            return False
