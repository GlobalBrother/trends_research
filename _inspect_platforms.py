from src.db.connection import get_session
from sqlalchemy import text

s = get_session()

print('--platforms--')
for r in s.execute(text('SELECT id, name FROM platforms ORDER BY id')).fetchall():
    print(r)

print('--content per platform (distinct)--')
for r in s.execute(text(
    'SELECT p.name, COUNT(DISTINCT c.id) FROM platforms p '
    'LEFT JOIN content c ON c.platform_id=p.id '
    'GROUP BY p.name ORDER BY 2 DESC'
)).fetchall():
    print(r)

print('--content x metric join row count (what the API actually returns) per platform--')
for r in s.execute(text(
    'SELECT p.name, COUNT(*) FROM platforms p '
    'JOIN content c ON c.platform_id=p.id '
    'LEFT JOIN content_metrics cm ON cm.content_id=c.id '
    'GROUP BY p.name ORDER BY 2 DESC'
)).fetchall():
    print(r)

print('--Instagram sample (keyword, geo, created_at)--')
for r in s.execute(text(
    "SELECT TOP 10 c.keyword, c.geo, c.created_at FROM content c "
    "JOIN platforms p ON p.id=c.platform_id WHERE p.name='Instagram'"
)).fetchall():
    print(r)

print('--Reddit sample (keyword, geo, created_at)--')
for r in s.execute(text(
    "SELECT TOP 10 c.keyword, c.geo, c.created_at FROM content c "
    "JOIN platforms p ON p.id=c.platform_id WHERE p.name='Reddit'"
)).fetchall():
    print(r)

print('--distinct geo values per platform--')
for r in s.execute(text(
    "SELECT p.name, c.geo, COUNT(*) FROM content c "
    "JOIN platforms p ON p.id=c.platform_id "
    "GROUP BY p.name, c.geo ORDER BY p.name, 3 DESC"
)).fetchall():
    print(r)

print('--trends per platform--')
for r in s.execute(text(
    'SELECT p.name, COUNT(t.id) FROM platforms p '
    'LEFT JOIN trends t ON t.platform_id=p.id '
    'GROUP BY p.name ORDER BY 2 DESC'
)).fetchall():
    print(r)

print('--HackerNews trends sample (topic, keyword, geo, extracted_at)--')
for r in s.execute(text(
    "SELECT TOP 10 t.topic, t.keyword, t.geo, t.extracted_at FROM trends t "
    "JOIN platforms p ON p.id=t.platform_id WHERE p.name='HackerNews' "
    "ORDER BY t.extracted_at DESC"
)).fetchall():
    print(r)

print('--News trends sample--')
for r in s.execute(text(
    "SELECT TOP 10 t.topic, t.keyword, t.geo, t.extracted_at FROM trends t "
    "JOIN platforms p ON p.id=t.platform_id WHERE p.name='News' "
    "ORDER BY t.extracted_at DESC"
)).fetchall():
    print(r)

s.close()
