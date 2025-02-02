```sqlCREATE TABLE vocabulary_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_name TEXT NOT NULL,
    json_value TEXT NOT NULL
);
```







```sql
-- Example insert statement for your data
INSERT INTO vocabulary_sets (set_name, json_value) 
VALUES (
    'Basic Set 1',
    '[
        {"level": 1, "chinese": "万物", "description": "wàn wù - all things"},
        {"level": 1, "chinese": "是", "description": "shì - is/are"},
        {"level": 1, "chinese": "藉着", "description": "jiè zhe - through/by means of"},
        {"level": 1, "chinese": "他", "description": "tā - him"},
        {"level": 1, "chinese": "造", "description": "zào - to create/make"}
    ]'
);
```



