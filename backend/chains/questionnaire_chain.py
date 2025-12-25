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
                return {"answers": answers}
    conn.close()
    return {"answers": {}}

def update_questionnaire(session_id):
    # 重新计算/填充问卷答案（占位）
    return {"status": "updated"}
