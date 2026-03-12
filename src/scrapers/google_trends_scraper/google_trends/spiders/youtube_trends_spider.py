import scrapy
import json
import re
import urllib.parse
from datetime import datetime
from ..items import GoogleTrendItem

class YoutubeTrendsSpider(scrapy.Spider):
    name = "youtube_trends"
    allowed_domains = ["www.youtube.com"]
    
    SEARCH_URL = "https://www.youtube.com/results"
    
    def __init__(self, keywords=None, *args, **kwargs):
        super(YoutubeTrendsSpider, self).__init__(*args, **kwargs)
        if isinstance(keywords, str):
            self.keywords = keywords.split(',')
        else:
            self.keywords = keywords or ["Survival trends", "Health trends"]

    def start_requests(self):
        for kw in self.keywords:
            # Sort by view count for the current month or week to find 'trending' content in niche
            # sp=CAM%253D is 'This month' + 'View count'
            params = {
                "search_query": kw,
                "sp": "CAM%3D" 
            }
            url = f"{self.SEARCH_URL}?{urllib.parse.urlencode(params)}"
            yield scrapy.Request(url=url, callback=self.parse, meta={'keyword': kw})

    def parse(self, response):
        self.logger.info(f"Parsing YouTube results for: {response.meta['keyword']}")
        
        # Extract ytInitialData JSON
        pattern = r'var ytInitialData = (\{.*?\});</script>'
        match = re.search(pattern, response.text)
        
        if not match:
            self.logger.error("Could not find ytInitialData in response")
            return

        try:
            data = json.loads(match.group(1))
            
            # Navigate to video results
            # data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
            
            results = []
            try:
                contents = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents']
                
                # Find the itemSectionRenderer that contains videoRenderer items
                video_items = []
                for content in contents:
                    if 'itemSectionRenderer' in content:
                        video_items.extend(content['itemSectionRenderer']['contents'])
                
                for item in video_items:
                    if 'videoRenderer' in item:
                        vr = item['videoRenderer']
                        title = vr.get('title', {}).get('runs', [{}])[0].get('text')
                        video_id = vr.get('videoId')
                        view_count_text = vr.get('viewCountText', {}).get('simpleText') or \
                                         vr.get('viewCountText', {}).get('runs', [{}])[0].get('text')
                        published_time = vr.get('publishedTimeText', {}).get('simpleText')
                        
                        if title and video_id:
                            results.append({
                                'title': title,
                                'video_id': video_id,
                                'views': view_count_text,
                                'published': published_time,
                                'url': f"https://www.youtube.com/watch?v={video_id}"
                            })
            except (KeyError, IndexError) as e:
                self.logger.error(f"Error navigating YouTube JSON: {e}")

            yield GoogleTrendItem(
                keyword=response.meta['keyword'],
                geo="Global", # YouTube search is mostly global unless restricted
                time_range="month",
                category=0,
                data_type="youtube_trends",
                results=results,
                extracted_at=datetime.now().isoformat()
            )

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse ytInitialData: {e}")
