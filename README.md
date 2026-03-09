# trends research

## Overview
This tool collects, analyzes, and visualizes trending topics across multiple platforms including Google Trends, YouTube, and X (Twitter). It uses a custom **Virality Score** and sentiment analysis to provide insights into emerging trends.

## Features
- **Data Collection**: Integrates Google Trends and multiple social media platform placeholders.
- **Analytics Engine**: Uses VADER for sentiment analysis and a custom algorithm for Virality Scoring.
- **Niche Discovery**: Clusters trending topics using K-Means and allows filtering by industry.
- **Visualization**: Interactive Streamlit dashboard with Plotly charts.
- **Export**: Export data as CSV or JSON.

## Project Structure
- `src/collector`: Modules for fetching data from various platforms.
- `src/analytics`: Algorithms for sentiment analysis and virality scores.
- `src/niche`: Tools for clustering topics and niche identification.
- `src/dashboard`: Streamlit application for visualization.

## How the Trend Detection Algorithm Works
The tool calculates a **Virality Score** for each topic based on two primary factors:
1.  **Growth Velocity**: The rate at which the topic's mentions or search interest is increasing.
2.  **Engagement Volume**: The total number of interactions (mentions, comments, likes) associated with the topic.

The formula used is:
`Score = (log(growth) * 0.7) + (log(engagement) * 0.3)`
This is then scaled to a 1-100 range for readability. Logarithmic scaling is applied to normalize high-frequency trends and prevent outliers from distorting the ranking.

## Installation

### Standard Installation
1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run the dashboard**:
    From the project root:
    ```powershell
    $env:PYTHONPATH="."
    streamlit run src/dashboard/app.py
    ```

### WSL (Windows Subsystem for Linux) Setup
1.  **Update your WSL environment**:
    ```bash
    sudo apt update && sudo apt upgrade -y
    sudo apt install python3 python3-pip python3-venv -y
    ```
2.  **Activate your virtual environment**:
    If your environment is stored in `.virtualenvs/trends_research`, run:
    ```bash
    source ~/.virtualenvs/trends_research/bin/activate
    ```
3.  **Install dependencies**:
    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```
4.  **Run the dashboard**:
    From the project root:
    ```bash
    export PYTHONPATH=$PYTHONPATH:.
    streamlit run src/dashboard/app.py
    ```

## Usage
- Use the sidebar to filter trends by niche keywords (e.g., "AI", "Crypto").
- Click "Refresh Trends" to fetch the latest data.
- Explore the "Niche Clustering" section to identify emerging micro-niches.
- Use the "Export" buttons to download the analyzed data.
