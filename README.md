# US Accidents MCP Server

An MCP server that enables LLMs to "talk to" a US Accidents dataset. Designed for an **Autonomous Vehicle Agent** that can assess driving risks based on historical accident data.

## Dataset

- **Source**: [US Accidents (2016-2023) on Kaggle](https://www.kaggle.com/datasets/sobhanmoosavi/us-accidents)

## Project Overview

1. **Data Science Notebook** (`data-science.ipynb`): Exploratory analysis revealing insights about:

   - Accident hotspots by state and city
   - Temporal patterns (rush hour, day of week)
   - Weather condition impacts
   - Congestion duration analysis

2. **Predictive Models**: Two machine learning models trained on the dataset:

   - **Severity Prediction Model** (`severity_model.pkl`): Binary classifier predicting whether an accident will be severe.
   - **Congestion Duration Model** (`congestion_duration_model.pkl`): Multi-class classifier predicting congestion duration.

3. **MCP Server** (`mcp_server/`): Allows LLMs to query the dataset through 10 specialized tools (possibly more in the future) designed for autonomous vehicle decision-making. Find the setup instructions for the MCP server below.

## MCP Tools Available

| Tool                           | Description                                                                                                                        |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| `get_accident_hotspots`        | Find locations with highest accident frequency                                                                                     |
| `get_accidents_near_location`  | Search accidents within radius of GPS coordinates                                                                                  |
| `get_temporal_risk_assessment` | Risk analysis based on time of day/week                                                                                            |
| `get_weather_risk_assessment`  | Risk analysis based on weather conditions                                                                                          |
| `analyze_route_risk`           | Assess accident risk along a planned route                                                                                         |
| `get_road_feature_risk`        | Analyze risk at junctions, crossings, etc.                                                                                         |
| `get_state_statistics`         | Comprehensive stats for any US state                                                                                               |
| `search_accident_descriptions` | Keyword search in accident descriptions                                                                                            |
| `get_covid_impact_analysis`    | Compare pre/during/post COVID patterns                                                                                             |
| `get_realtime_risk_score`      | **Primary AV tool**: Combined risk score with recommendations, however not completely real time since the dataset cuts off in 2023 |

## Start

### 1. Install Dependencies

```bash
cd mcp_server
pip install -e .
```

Or install the MCP library directly:

```bash
pip install "mcp[cli]"
```

### 2. Build the Database

Convert the CSV to an optimized SQLite database:

```bash
# Make sure US_Accidents_March23.csv is downloaded from Kaggle and extracted from zip in the project root
python -m mcp_server.build_database
```

This creates `mcp_server/accidents.db` (~3.2GB).

### 3. Test the Server

```bash
# Test that the server starts correctly
python -m mcp_server.server
```

### 4. Connect to Claude Desktop

Copy the configuration to Claude Desktop's config:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

or directly edit in the Claude Desktop App settings.

```json
{
  "mcpServers": {
    "us-accidents": {
      "command": "python", // or full path to python executable
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/cs451-final-project"
    }
  }
}
```

Tools will be available once Claude Desktop is restarted.

## Example Conversations

### Autonomous Vehicle Route Planning

> **You**: I'm planning a route from San Francisco to Los Angeles. It's currently 5pm on a Friday and it's raining. What should my AV be aware of?

Claude can call multiple tools:

- `analyze_route_risk` with waypoints
- `get_realtime_risk_score` for SF and LA
- `get_weather_risk_assessment` for rain conditions
- `get_temporal_risk_assessment` for Friday rush hour

### More examples

> What's the safest time to drive through Miami?
> How did COVID affect accident rates in California?

## Demo Recordings

The demo recordings can be found in the `recordings/` directory. One video goes over simple questions with one tool called each, and the other video goes over a scenario where multiple tools are called in sequence to help an autonomous vehicle plan a safe route.

## Authors

- Hargun Singh Mujral
- Kushal Mujral
