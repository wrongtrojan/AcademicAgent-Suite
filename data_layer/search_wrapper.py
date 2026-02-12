import sys
import json
from vector_search import AcademicSearcher

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No params provided"}))
        return

    params = json.loads(sys.argv[1])
    query = params.get("query")
    top_k = params.get("top_k", 5)
    preferences = params.get("preferences")

    try:
        searcher = AcademicSearcher()
        results = searcher.search(query=query, top_k=top_k, preferences=preferences)
        print(json.dumps(results))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))

if __name__ == "__main__":
    main()