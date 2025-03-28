from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
import datetime
import httpx
import asyncio
import copy
import json
import io
import matplotlib.pyplot as plt

app = FastAPI()

GITHUB_EVENTS_URL = "https://api.github.com/repos/{owner}/{repo}/events"
SPECIFIC_EVENTS = {"WatchEvent", "PullRequestEvent", "IssuesEvent"}  # Define event types
event_type_list = {}
events_list = {}
repositories = {}
repo_id_name_map = {}


async def fetch_github_events(owner: str, repo: str):
    if repo == "" and owner == "":
        url = "https://api.github.com/events"
    else:
        url = GITHUB_EVENTS_URL.format(owner=owner, repo=repo)
    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(url)
            if response.status_code == 200:
                events = response.json()
                for n, event in enumerate(events):
                    if event.get("type") in SPECIFIC_EVENTS:
                        yield f"data: {event}\n\n"
                        process_data(copy.deepcopy(event))
            await asyncio.sleep(5)


def process_data(event: dict):
    if event["type"] not in event_type_list:
        event_type_list[event["type"]] = []
    event_type_list[event["type"]].append(event)
    timestamp = datetime.datetime.strptime(event['created_at'], "%Y-%m-%dT%H:%M:%SZ")
    while timestamp in events_list:
        timestamp += datetime.timedelta(microseconds=1)
    events_list[timestamp] = event
    match event["type"]:
        case "PullRequestEvent":
            repository = event['repo']['name']
            if repository not in repositories:
                repositories[repository] = []
            repositories[repository].append(timestamp)
            repo_id_name_map[event['repo']['id']] = repository
        case _:
            pass


def calc_pr(repo: str):
    try:
        times = repositories[repo]
    except KeyError:
        return f"No records for repository '{repo}'"
    times.sort()
    div = max(len(times) - 1, 1)
    return f"Average time between pull requests for repository: '{repo}' is: {round((times[-1] - times[0]) / div, 2)}s"


def calc_events(minutes: int):
    for timestamp in events_list.keys():
        if datetime.datetime.now() - datetime.timedelta(minutes=minutes) < timestamp:
            yield events_list[timestamp]


def generate_chart():
    fig, ax = plt.subplots()
    ax.bar(events_list.keys(), events_list.values(), color=["blue", "red"])
    ax.set_ylabel("Event Count")
    ax.set_title("GitHub Event Statistics")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


@app.get("/events/{minutes}")
async def get_events(minutes: int):
    return list(calc_events(minutes))


@app.get("/pr-time/{repo_id}")
async def pr_time(repo_id: int):
    repo = repo_id_name_map[repo_id]
    return calc_pr(repo)


@app.get("/pr-time/{owner}/{repo}")
async def pr_time(owner: str | int, repo: str | None):
    repo = f"{owner}/{repo}"
    return calc_pr(repo)


@app.get("/stream")
async def stream():
    return StreamingResponse(fetch_github_events("", ""), media_type="text/event-stream")


@app.get("/stream/{owner}/{repo}")
async def stream_github_events(owner: str, repo: str):
    return StreamingResponse(fetch_github_events(owner, repo), media_type="text/event-stream")


@app.get("/stats")
def get_event_stats():
    return events_list


@app.get("/chart")
def get_event_chart():
    buf = generate_chart()
    return StreamingResponse(buf, media_type="image/png")


@app.get("/")
def home():
    return HTMLResponse(
        content="""
        <html>
        <head>
            <title>GitHub Events Visualization</title>
        </head>
        <body>
            <h1>GitHub Events Visualization</h1>
            <p><a href="/stats">View JSON Stats</a></p>
            <p><a href="/chart">View Event Chart</a></p>
        </body>
        </html>
        """,
    )
