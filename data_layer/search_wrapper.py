# data_layer/search_wrapper.py
import sys
import json
import torch # 仅在子进程环境运行
from vector_search import AcademicSearcher

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No params provided"}))
        return

    params = json.loads(sys.argv[1])
    query = params.get("query")
    asset_id = params.get("asset_id")
    top_k = params.get("top_k", 5)

    try:
        searcher = AcademicSearcher()
        results = searcher.search(query=query, asset_id=asset_id, top_k=top_k)
        # 确保输出最后一行是 JSON
        print(json.dumps(results))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))

if __name__ == "__main__":
    main()