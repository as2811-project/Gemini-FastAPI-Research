import os
import json
from fastapi import FastAPI, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY is None:
    raise ValueError("GEMINI_API_KEY is not set in your environment variables.")

client = genai.Client(api_key=GEMINI_API_KEY)

class Queries(BaseModel):
    wide_queries: list[str]
    deep_queries: list[str]

class ReportRequest(BaseModel):
    topic: str
    width: int
    depth: int
    deepdive_topic: str

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def generate_queries(topic: str, width: int, depth: int, deepdive_topic: str):
    """
    :param topic: Research Topic
    :param width: Width of Research
    :param depth: Depth of Research
    :param deepdive_topic: Topic that the user wants to dive deeper into
    :return: list of queries to be used downstream by the generate context function
    """
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=(
            f"You are an expert in topic: {topic}. Your task is to generate search queries "
            f"to aid the user's research on said topic. The user will provide you research width and depth. "
            f"Width indicates how wide the research needs to be. Depth indicates how deep the research needs to be "
            f"for a specific topic. You need to generate {width} search queries to cover the width of the research "
            f"and {depth} search queries to go deeper into the subtopic: {deepdive_topic}."
        ),
        config={
            'response_mime_type': 'application/json',
            'response_schema': list[Queries],
        }
    )
    return json.loads(response.text)

def generate_context(search_query: str):
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=search_query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearchRetrieval)]
        )
    )
    return response.text, response.candidates[0].grounding_metadata.grounding_chunks

def generate_final_report(topic: str, deepdive_topic: str, total_context: list, citations: list):
    sys_instruct = (
        f"You are an expert analyst in the topic: {topic}. You've been given a lot of context (which you produced earlier) "
        f"supporting the user's research on said topic. With this information, generate a detailed (1000 words) report as instructed. "
        f"Be sure to include all sources, persons, objects etc in the report. Additionally, you must dive deeper into {deepdive_topic} "
        f"as that is what the user would like to dive deeper into. You MUST include a references section and appropriately add citations. "
        f"Use the Citations object provided to you, each citation has a title and a URI, the citations in the report MUST be hyperlinked "
        f"with the corresponding uri so that the user can follow it if necessary. Ensure that the report itself adheres to the user's "
        f"requirements and does not deviate away from the research's goals. Feel free to provide tables if required."
    )
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(system_instruction=sys_instruct),
        contents=f"Context: {json.dumps(total_context)} Citations: {json.dumps(citations)}"
    )
    return response.text

class HealthCheck(BaseModel):
    message: str = "OK"
@app.get("/health", status_code=status.HTTP_200_OK, response_model=HealthCheck)
async def health() -> HealthCheck:
    """
    Health Check endpoint
    :return: 200
    """
    return HealthCheck(status="OK")
@app.post("/research")
async def generate_report_sse(report_request: ReportRequest):
    """
    SSE endpoint that streams citations as they are retrieved.
    After processing all queries, the final report is sent as the last event.
    """
    def event_generator():
        try:
            search_queries = generate_queries(
                report_request.topic,
                report_request.width,
                report_request.depth,
                report_request.deepdive_topic
            )
            total_context = []
            citations_set = {}

            for query_type in ["wide_queries", "deep_queries"]:
                for query in search_queries[0][query_type]:
                    context, source_list = generate_context(query)
                    total_context.append(context)
                    for src in source_list:
                        citation = {"title": src.web.title, "uri": src.web.uri}
                        if citation["uri"] not in citations_set:
                            citations_set[citation["uri"]] = citation
                            # Yield a citation event.
                            yield f"data: {json.dumps({'citation': citation})}\n\n"
            citations_list = list(citations_set.values())

            report_text = generate_final_report(
                report_request.topic,
                report_request.deepdive_topic,
                total_context,
                citations_list
            )
            # Yield the final report event.
            yield f"data: {json.dumps({'report': report_text})}\n\n"
        except Exception as e:
            # Yield an error event if needed.
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
