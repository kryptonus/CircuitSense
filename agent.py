from google.adk.agents import Agent
from google.adk.tools import google_search

root_agent = Agent(
    model="gemini-2.0-flash",
    name="circuitsense",
    description="Real-time electronics assistant with vision and search",
    instruction="You are CircuitSense, an expert electronics engineering assistant. Help users identify components, debug circuits, and find datasheets.",
    tools=[google_search],
)
