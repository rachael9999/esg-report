def get_questionnaire(session_id):
    # 查询数据库，返回问卷答案
    from db.db import get_conn
    conn = get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT answers FROM answers WHERE session_id=%s ORDER BY created_at DESC LIMIT 1", (session_id,))
            row = cur.fetchone()
            if row and row[0]:
                import json
                answers = row[0]
                if isinstance(answers, str):
                    answers = json.loads(answers)
                sources = {}
                conflicts = {}
                if isinstance(answers, dict):
                    sources = answers.pop("_sources", {})
                    conflicts = answers.pop("_conflicts", {})
                return {
                    "answers": answers,
                    "answer_sources": sources,
                    "answer_conflicts": conflicts
                }
    conn.close()
    return {"answers": {}, "answer_sources": {}, "answer_conflicts": {}}

def update_questionnaire(session_id):
    # 重新计算/填充问卷答案（占位）
    return {"status": "updated"}
