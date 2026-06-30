"""
Base Agent Class for FIFA World Cup Multi-Agent System (Langchain 1.2 Compatible)
Provides common infrastructure: memory, tool calling, async execution, caching
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, asdict
import redis
from langchain_anthropic import ChatAnthropic
from langchain.tools import BaseTool, tool
from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class AgentMetrics:
    """Metrics for agent performance tracking"""
    agent_name: str
    cycle_timestamp: datetime
    cycle_duration_ms: int
    tool_calls_count: int = 0
    errors_count: int = 0
    cache_hit_rate: float = 0.0
    status: str = "SUCCESS"  # SUCCESS, WARNING, ERROR
    error_message: Optional[str] = None


class BaseAgent(ABC):
    """
    Base class for all FIFA World Cup agents (Langchain 1.2+)

    Responsibilities:
    - Manage LLM connection (Claude via LangChain)
    - Handle tool definitions and calling
    - Implement memory and context management
    - Cache query results in Redis
    - Track metrics for monitoring
    - Execute async operations in parallel
    """

    def __init__(
        self,
        agent_name: str,
        model: str = "claude-opus-4-8",
        max_iterations: int = 10,
        temperature: float = 0.2,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        cache_ttl: int = 300,
    ):
        """
        Initialize base agent

        Args:
            agent_name: Name of the agent (for logging/tracking)
            model: Claude model ID to use
            max_iterations: Max tool calls before stopping
            temperature: LLM temperature (lower = more deterministic)
            redis_host: Redis connection host
            redis_port: Redis connection port
            cache_ttl: Cache TTL in seconds
        """
        self.agent_name = agent_name
        self.model = model
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.cache_ttl = cache_ttl

        # Initialize LLM with tool binding support
        self.llm = ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=2048,
        )

        # Initialize Redis for caching
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            self.redis_client.ping()
        except Exception as e:
            logger.warning(f"{agent_name}: Redis connection failed: {e}")
            self.redis_client = None

        # Tools registry (subclasses will populate)
        self.tools: List[BaseTool] = []
        self.tool_map: Dict[str, Callable] = {}

        # Metrics tracking
        self.metrics: Optional[AgentMetrics] = None
        self.cycle_start_time: Optional[datetime] = None

        logger.info(f"Initialized {agent_name} agent with model {model}")

    def register_tools(self, tools: List[BaseTool]) -> None:
        """
        Register tools for this agent

        Args:
            tools: List of LangChain Tool objects
        """
        self.tools = tools
        # Build tool map for easy lookup during execution
        for tool in tools:
            if hasattr(tool, 'name'):
                self.tool_map[tool.name] = tool
        logger.info(f"{self.agent_name}: Registered {len(tools)} tools")

    def _get_cache_key(self, operation: str, **kwargs) -> str:
        """Generate Redis cache key"""
        key_parts = [self.agent_name, operation]
        for k, v in sorted(kwargs.items()):
            if isinstance(v, (str, int, float)):
                key_parts.append(f"{k}:{v}")
        return ":".join(key_parts)

    def cache_get(self, operation: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get cached result from Redis"""
        if self.redis_client is None:
            return None

        cache_key = self._get_cache_key(operation, **kwargs)
        try:
            cached = self.redis_client.get(cache_key)
            if cached:
                logger.debug(f"Cache HIT: {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache GET error: {e}")
        return None

    def cache_set(self, operation: str, value: Dict[str, Any], **kwargs) -> bool:
        """Set cache value in Redis"""
        if self.redis_client is None:
            return False

        cache_key = self._get_cache_key(operation, **kwargs)
        try:
            self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(value)
            )
            logger.debug(f"Cache SET: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"Cache SET error: {e}")
            return False

    def start_cycle(self) -> None:
        """Start a new agent cycle (for metrics)"""
        self.cycle_start_time = datetime.utcnow()
        self.metrics = AgentMetrics(
            agent_name=self.agent_name,
            cycle_timestamp=self.cycle_start_time,
            cycle_duration_ms=0,
        )

    def end_cycle(self, status: str = "SUCCESS", error: Optional[str] = None) -> AgentMetrics:
        """End agent cycle and compute metrics"""
        if not self.metrics:
            self.start_cycle()

        elapsed_ms = int((datetime.utcnow() - self.cycle_start_time).total_seconds() * 1000)
        self.metrics.cycle_duration_ms = elapsed_ms
        self.metrics.status = status
        self.metrics.error_message = error

        return self.metrics

    async def run_agent_loop(
        self,
        system_prompt: str,
        user_input: str,
    ) -> Dict[str, Any]:
        """
        Execute agent loop: ask LLM, call tools, repeat until done.

        Args:
            system_prompt: System prompt for the LLM
            user_input: User query/input

        Returns:
            Final response from agent
        """
        messages: List[BaseMessage] = [HumanMessage(content=user_input)]
        tool_calls_count = 0

        # Bind tools to LLM
        llm_with_tools = self.llm.bind_tools(
            self.tools,
            tool_choice="auto",
        ) if self.tools else self.llm

        for iteration in range(self.max_iterations):
            logger.debug(f"{self.agent_name}: Iteration {iteration + 1}")

            try:
                # Get LLM response
                response = await asyncio.to_thread(
                    llm_with_tools.invoke,
                    {"messages": messages},
                )

                messages.append(response)

                # Check if LLM wants to use tools
                if not hasattr(response, 'tool_calls') or not response.tool_calls:
                    # No more tool calls, return response
                    return {
                        "status": "SUCCESS",
                        "response": response.content if hasattr(response, 'content') else str(response),
                        "tool_calls": tool_calls_count,
                        "iterations": iteration + 1,
                    }

                # Execute tool calls
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get("name") or tool_call.get("type")
                    tool_input = tool_call.get("args", {})

                    logger.debug(f"{self.agent_name}: Calling tool {tool_name}")

                    try:
                        if tool_name in self.tool_map:
                            # Call registered tool
                            tool = self.tool_map[tool_name]
                            result = await asyncio.to_thread(tool.run, **tool_input)
                        else:
                            result = f"Tool {tool_name} not found"

                        # Add tool result to messages
                        messages.append(ToolMessage(
                            content=json.dumps(result) if not isinstance(result, str) else result,
                            tool_use_id=tool_call.get("id", tool_name),
                        ))

                        tool_calls_count += 1

                    except Exception as e:
                        logger.error(f"{self.agent_name}: Tool error: {e}")
                        messages.append(ToolMessage(
                            content=f"Error: {str(e)}",
                            tool_use_id=tool_call.get("id", tool_name),
                        ))

            except Exception as e:
                logger.error(f"{self.agent_name}: Agent loop error: {e}")
                return {
                    "status": "ERROR",
                    "error": str(e),
                    "tool_calls": tool_calls_count,
                    "iterations": iteration + 1,
                }

        logger.warning(f"{self.agent_name}: Max iterations reached")
        return {
            "status": "WARNING",
            "message": "Max iterations reached",
            "tool_calls": tool_calls_count,
            "iterations": self.max_iterations,
        }

    @abstractmethod
    async def run(self) -> Dict[str, Any]:
        """
        Main agent execution method.
        Subclasses implement specific agent logic.
        """
        pass
