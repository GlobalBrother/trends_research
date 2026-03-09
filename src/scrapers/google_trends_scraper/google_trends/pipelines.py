import json
from datetime import datetime

class GoogleTrendsPipeline:
    def process_item(self, item, spider):
        item['extracted_at'] = datetime.now().isoformat()
        return item

class JSONLPipeline:
    def open_spider(self, spider):
        # We use 'w' to overwrite the file for new keyword runs, 
        # or we could keep 'a' for history but the dashboard might get cluttered.
        # Given the previous context, 'a' was used. Let's keep 'a' but maybe 
        # the user wants fresh data for the selected niche.
        # Actually, if we want to ONLY show the selected niche, we might want to clear it.
        # But wait, collect_all reads the whole file.
        self.file = open('trends_output.jsonl', 'a', encoding='utf-8')

    def close_spider(self, spider):
        self.file.close()

    def process_item(self, item, spider):
        line = json.dumps(dict(item)) + "\n"
        self.file.write(line)
        return item

# Example PostgreSQL Pipeline (Placeholders)
class PostgreSQLPipeline:
    def __init__(self, db_uri):
        self.db_uri = db_uri

    @classmethod
    def from_crawler(cls, crawler):
        return cls(db_uri=crawler.settings.get('POSTGRES_URI'))

    def open_spider(self, spider):
        # Setup DB connection
        pass

    def close_spider(self, spider):
        # Close DB connection
        pass

    def process_item(self, item, spider):
        # Insert logic
        return item
