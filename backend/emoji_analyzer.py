"""
Smart Emoji Analyzer - picks contextually relevant reaction emojis
based on reel captions, hashtags, and content metadata.
"""
import re
import random
import requests
import json

# Category → emoji mapping (each category can have multiple emoji options)
CATEGORY_EMOJIS = {
    "funny":        ["😂", "🤣", "😆"],
    "fire":         ["🔥", "💯", "🔥"],
    "love":         ["❤️", "😍", "🥰"],
    "sad":          ["😢", "🥺", "💔"],
    "angry":        ["😡", "💢"],
    "fitness":      ["💪", "🔥", "👏"],
    "food":         ["😋", "🤤", "😍"],
    "travel":       ["😍", "🌍", "✨"],
    "nature":       ["😍", "🌿", "✨"],
    "music":        ["🔥", "🎶", "🙌"],
    "dance":        ["🔥", "💃", "🙌"],
    "fashion":      ["😍", "🔥", "✨"],
    "beauty":       ["😍", "✨", "🔥"],
    "motivational": ["👏", "💪", "🙌"],
    "shocking":     ["😮", "🤯", "😱"],
    "talent":       ["👏", "🔥", "😮"],
    "cute":         ["🥰", "😍", "❤️"],
    "pets":         ["🥰", "😍", "❤️"],
    "sports":       ["🔥", "💪", "👏"],
    "gaming":       ["🔥", "🎮", "💯"],
    "art":          ["😍", "✨", "👏"],
    "tech":         ["🔥", "😮", "💯"],
    "celebration":  ["🎉", "🙌", "👏"],
    "relatable":    ["😂", "💯", "👏"],
    "aesthetic":    ["✨", "😍", "🔥"],
    "throwback":    ["❤️", "🥺", "😍"],
    "friendship":   ["❤️", "🙌", "😂"],
    "couple":       ["❤️", "🥰", "😍"],
    "fail":         ["😂", "🤣", "💀"],
    "scary":        ["😱", "😮", "🫣"],
    "satisfying":   ["😍", "✨", "🔥"],
    "cringe":       ["😂", "💀", "🤣"],
}

# Keywords mapped to categories (lowercase)
KEYWORD_CATEGORIES = {
    # Funny / Comedy
    "funny": "funny", "comedy": "funny", "lol": "funny", "lmao": "funny",
    "meme": "funny", "memes": "funny", "humor": "funny", "humour": "funny",
    "joke": "funny", "jokes": "funny", "hilarious": "funny", "haha": "funny",
    "rofl": "funny", "skit": "funny", "parody": "funny", "prank": "funny",
    "blooper": "funny", "bloopers": "funny", "viral": "funny",
    "comedyreels": "funny", "funnyreels": "funny", "trolling": "funny",
    "standup": "funny", "funnymemes": "funny", "laughing": "funny",

    # Fire / Lit / Hype
    "fire": "fire", "lit": "fire", "hot": "fire", "heat": "fire",
    "trending": "fire", "vibes": "fire", "vibe": "fire", "savage": "fire",
    "dope": "fire", "sick": "fire", "insane": "fire", "crazy": "fire",
    "epic": "fire", "legend": "fire", "legendary": "fire", "goat": "fire",
    "goated": "fire", "banger": "fire", "slaps": "fire", "hardest": "fire",
    "beast": "fire", "killer": "fire", "badass": "fire",

    # Love / Romance
    "love": "love", "romance": "love", "romantic": "love", "heart": "love",
    "kiss": "love", "bae": "love", "soulmate": "love", "forever": "love",
    "boyfriend": "love", "girlfriend": "love", "hubby": "love", "wifey": "love",
    "relationship": "love", "crush": "love", "iloveyou": "love",
    "loveyou": "love", "lovestory": "love", "couplegoals": "couple",

    # Couple
    "couple": "couple", "couples": "couple", "together": "couple",
    "anniversary": "couple", "proposal": "couple", "wedding": "couple",
    "engaged": "couple", "married": "couple",

    # Sad / Emotional
    "sad": "sad", "crying": "sad", "emotional": "sad", "heartbreak": "sad",
    "breakup": "sad", "miss": "sad", "missing": "sad", "lonely": "sad",
    "pain": "sad", "hurt": "sad", "depressed": "sad", "tears": "sad",
    "rip": "sad", "goodbye": "sad", "loss": "sad", "grief": "sad",
    "broken": "sad", "feels": "sad", "deep": "sad", "overthinking": "sad",

    # Angry
    "angry": "angry", "rage": "angry", "furious": "angry", "mad": "angry",
    "pissed": "angry", "annoyed": "angry", "frustrated": "angry",

    # Fitness / Gym
    "fitness": "fitness", "gym": "fitness", "workout": "fitness",
    "fit": "fitness", "muscle": "fitness", "bodybuilding": "fitness",
    "gains": "fitness", "bulk": "fitness", "shredded": "fitness",
    "cardio": "fitness", "training": "fitness", "crossfit": "fitness",
    "exercise": "fitness", "fitfam": "fitness", "fitnessmotivation": "fitness",
    "lifting": "fitness", "deadlift": "fitness", "squat": "fitness",
    "abs": "fitness", "yoga": "fitness", "running": "fitness",
    "marathon": "fitness", "pushup": "fitness", "pullup": "fitness",
    "gymlife": "fitness", "gymmotivation": "fitness", "nopainnogain": "fitness",

    # Food / Cooking
    "food": "food", "cooking": "food", "recipe": "food", "recipes": "food",
    "cook": "food", "chef": "food", "yummy": "food", "delicious": "food",
    "tasty": "food", "foodie": "food", "foodporn": "food", "baking": "food",
    "dessert": "food", "pizza": "food", "burger": "food", "sushi": "food",
    "cake": "food", "chocolate": "food", "biryani": "food", "masala": "food",
    "spicy": "food", "breakfast": "food", "lunch": "food", "dinner": "food",
    "snack": "food", "streetfood": "food", "homemade": "food",
    "restaurant": "food", "eating": "food", "mukbang": "food",

    # Travel / Adventure
    "travel": "travel", "traveling": "travel", "travelling": "travel",
    "wanderlust": "travel", "explore": "travel", "adventure": "travel",
    "vacation": "travel", "holiday": "travel", "trip": "travel",
    "roadtrip": "travel", "backpacking": "travel", "tourist": "travel",
    "beach": "travel", "mountain": "travel", "mountains": "travel",
    "hiking": "travel", "flight": "travel", "airport": "travel",
    "passport": "travel", "destination": "travel", "paradise": "travel",
    "island": "travel", "camping": "travel", "trekking": "travel",

    # Nature
    "nature": "nature", "sunset": "nature", "sunrise": "nature",
    "ocean": "nature", "sea": "nature", "forest": "nature", "sky": "nature",
    "flowers": "nature", "rain": "nature", "snow": "nature", "garden": "nature",
    "wildlife": "nature", "earth": "nature", "green": "nature",
    "waterfall": "nature", "lake": "nature", "river": "nature",

    # Music
    "music": "music", "song": "music", "singer": "music", "rap": "music",
    "hiphop": "music", "rock": "music", "pop": "music", "edm": "music",
    "dj": "music", "beats": "music", "melody": "music", "guitar": "music",
    "piano": "music", "drums": "music", "concert": "music", "album": "music",
    "playlist": "music", "remix": "music", "cover": "music",
    "singing": "music", "vocals": "music", "rapper": "music",

    # Dance
    "dance": "dance", "dancing": "dance", "dancer": "dance",
    "choreography": "dance", "hiphop": "dance", "salsa": "dance",
    "twerk": "dance", "ballet": "dance", "breakdance": "dance",
    "moves": "dance", "groove": "dance",

    # Fashion / Style
    "fashion": "fashion", "style": "fashion", "outfit": "fashion",
    "ootd": "fashion", "drip": "fashion", "streetwear": "fashion",
    "designer": "fashion", "model": "fashion", "modeling": "fashion",
    "dress": "fashion", "sneakers": "fashion", "shoes": "fashion",
    "accessories": "fashion", "trendy": "fashion", "lookbook": "fashion",
    "fashionista": "fashion", "grwm": "fashion", "getreadywithme": "fashion",

    # Beauty / Makeup
    "beauty": "beauty", "makeup": "beauty", "skincare": "beauty",
    "glow": "beauty", "glowup": "beauty", "transformation": "beauty",
    "makeover": "beauty", "cosmetics": "beauty", "tutorial": "beauty",
    "hairstyle": "beauty", "hair": "beauty", "nails": "beauty",

    # Motivation / Inspiration
    "motivation": "motivational", "motivational": "motivational",
    "inspiration": "motivational", "inspirational": "motivational",
    "hustle": "motivational", "grind": "motivational", "success": "motivational",
    "mindset": "motivational", "discipline": "motivational",
    "hardwork": "motivational", "never give up": "motivational",
    "believe": "motivational", "dream": "motivational", "dreams": "motivational",
    "goals": "motivational", "ambition": "motivational", "boss": "motivational",
    "entrepreneur": "motivational", "millionaire": "motivational",
    "sigma": "motivational", "grindset": "motivational",
    "selfimprovement": "motivational", "growth": "motivational",

    # Shocking / Surprising
    "shocking": "shocking", "unbelievable": "shocking", "omg": "shocking",
    "wtf": "shocking", "impossible": "shocking", "mindblowing": "shocking",
    "unexpected": "shocking", "plot twist": "shocking", "twist": "shocking",
    "whatjusthappened": "shocking", "noway": "shocking",

    # Talent / Skills
    "talent": "talent", "talented": "talent", "skills": "talent",
    "skill": "talent", "amazing": "talent", "incredible": "talent",
    "impressive": "talent", "nextlevel": "talent", "wow": "talent",
    "masterpiece": "talent", "prodigy": "talent", "genius": "talent",
    "insanetalent": "talent", "satisfying": "satisfying",

    # Cute / Adorable
    "cute": "cute", "adorable": "cute", "aww": "cute", "baby": "cute",
    "babies": "cute", "precious": "cute", "sweet": "cute", "lovely": "cute",
    "cutest": "cute", "wholesome": "cute",

    # Pets / Animals
    "pet": "pets", "pets": "pets", "dog": "pets", "dogs": "pets",
    "puppy": "pets", "cat": "pets", "cats": "pets", "kitten": "pets",
    "animal": "pets", "animals": "pets", "dogsofinstagram": "pets",
    "catsofinstagram": "pets", "pup": "pets", "doggo": "pets",
    "goodboy": "pets", "goodgirl": "pets",

    # Sports
    "sports": "sports", "cricket": "sports", "football": "sports",
    "soccer": "sports", "basketball": "sports", "nba": "sports",
    "ipl": "sports", "goal": "sports", "score": "sports",
    "match": "sports", "game": "sports", "champion": "sports",
    "winner": "sports", "trophy": "sports", "worldcup": "sports",
    "athlete": "sports", "messi": "sports", "ronaldo": "sports",
    "virat": "sports", "dhoni": "sports", "kohli": "sports",

    # Gaming
    "gaming": "gaming", "gamer": "gaming", "gameplay": "gaming",
    "playstation": "gaming", "xbox": "gaming", "pc": "gaming",
    "valorant": "gaming", "fortnite": "gaming", "minecraft": "gaming",
    "pubg": "gaming", "bgmi": "gaming", "freefire": "gaming",
    "gta": "gaming", "cod": "gaming", "esports": "gaming",

    # Art / Creative
    "art": "art", "artist": "art", "artwork": "art", "drawing": "art",
    "painting": "art", "sketch": "art", "creative": "art",
    "design": "art", "illustration": "art", "digital": "art",
    "photography": "art", "photo": "art", "photographer": "art",
    "edit": "art", "editing": "art", "photoshop": "art",

    # Tech
    "tech": "tech", "technology": "tech", "gadget": "tech", "gadgets": "tech",
    "iphone": "tech", "android": "tech", "samsung": "tech", "apple": "tech",
    "laptop": "tech", "coding": "tech", "programming": "tech",
    "developer": "tech", "ai": "tech", "robot": "tech", "innovation": "tech",
    "setup": "tech", "unboxing": "tech",

    # Celebration / Party
    "celebration": "celebration", "party": "celebration", "birthday": "celebration",
    "newyear": "celebration", "festival": "celebration", "diwali": "celebration",
    "christmas": "celebration", "holi": "celebration", "eid": "celebration",
    "congratulations": "celebration", "congrats": "celebration",
    "celebrate": "celebration", "win": "celebration",

    # Relatable
    "relatable": "relatable", "meirl": "relatable", "same": "relatable",
    "mood": "relatable", "facts": "relatable", "real": "relatable",
    "truth": "relatable", "literally": "relatable", "sameenergy": "relatable",
    "accurate": "relatable", "truestory": "relatable",
    "everyoneknows": "relatable", "sodamnrelatable": "relatable",

    # Aesthetic
    "aesthetic": "aesthetic", "aesthetics": "aesthetic", "vlog": "aesthetic",
    "cinematic": "aesthetic", "dreamy": "aesthetic", "cozy": "aesthetic",
    "minimal": "aesthetic", "vintage": "aesthetic", "retro": "aesthetic",
    "slowmotion": "aesthetic", "golden": "aesthetic", "aura": "aesthetic",

    # Throwback
    "throwback": "throwback", "tbt": "throwback", "memories": "throwback",
    "nostalgia": "throwback", "nostalgic": "throwback", "childhood": "throwback",
    "oldschool": "throwback", "backintheday": "throwback", "remember": "throwback",

    # Friendship
    "friends": "friendship", "bestfriend": "friendship", "bestie": "friendship",
    "bff": "friendship", "squad": "friendship", "gang": "friendship",
    "crew": "friendship", "friendshipgoals": "friendship", "bros": "friendship",
    "bromance": "friendship", "girlgang": "friendship",

    # Fail / Epic fail
    "fail": "fail", "fails": "fail", "epicfail": "fail", "oops": "fail",
    "clumsy": "fail", "facepalm": "fail", "disaster": "fail",

    # Scary / Horror
    "scary": "scary", "horror": "scary", "creepy": "scary", "ghost": "scary",
    "haunted": "scary", "paranormal": "scary", "spooky": "scary",

    # Satisfying
    "satisfying": "satisfying", "oddlysatisfying": "satisfying",
    "asmr": "satisfying", "soothing": "satisfying", "calming": "satisfying",
    "relaxing": "satisfying", "smooth": "satisfying",

    # Cringe
    "cringe": "cringe", "cringy": "cringe", "cringeworthy": "cringe",
    "awkward": "cringe", "secondhandcringe": "cringe",
}

# Default emojis for when no category matches (positive general reactions)
DEFAULT_EMOJIS = ["❤️", "🔥", "😍", "👏", "💯", "✨", "🙌"]


def extract_text_content(caption_text: str) -> list:
    """Extract individual words and hashtags from caption text."""
    if not caption_text:
        return []

    # Lowercase everything
    text = caption_text.lower()

    # Extract hashtags (without the # symbol)
    hashtags = re.findall(r'#(\w+)', text)

    # Extract regular words (letters only, 3+ chars)
    words = re.findall(r'[a-zA-Z]{3,}', text)

    return hashtags + words


def get_smart_emoji(caption_text: str, comments: list = None, message_text: str = None, fallback_emojis: list = None, use_random_fallback: bool = False) -> str:
    """
    Main entry point: given reel caption text, comments, and the sender's companion message,
    returns a contextually appropriate emoji reaction.
    
    Args:
        caption_text: The reel's caption/description text including hashtags
        comments: A list of comment strings fetched from the reel
        message_text: The text accompanying the Reel share sent by the friend
        fallback_emojis: Optional list of emojis to use if no content match
        use_random_fallback: Whether to choose randomly from fallback_emojis or pick the first one
        
    Returns:
        A single emoji string
    """
    if comments is None:
        comments = []
    if not fallback_emojis:
        fallback_emojis = DEFAULT_EMOJIS

    # 1. Reverse-map category emojis to map direct emoji sentiments in comments/captions
    EMOJI_TO_CATEGORY = {}
    known_emoji_set = set(DEFAULT_EMOJIS)
    for category, emojis in CATEGORY_EMOJIS.items():
        known_emoji_set.update(emojis)
        for emoji in emojis:
            EMOJI_TO_CATEGORY[emoji] = category

    # 2. Extract actual emojis from companion message text, caption, and comments
    found_emojis = []
    found_message_emojis = []
    
    # Check for direct emojis in companion message text (highest priority)
    if message_text:
        for emoji in known_emoji_set:
            if emoji in message_text:
                count = message_text.count(emoji)
                for _ in range(count):
                    found_message_emojis.append(emoji)
                    
    # Check for emojis in caption/comments (secondary priority)
    combined_reel_text = (caption_text or "") + " " + " ".join(comments)
    for emoji in known_emoji_set:
        if emoji in combined_reel_text:
            count = combined_reel_text.count(emoji)
            for _ in range(count):
                found_emojis.append(emoji)

    # 3. Score categories by checking if keywords/phrases appear in the texts
    category_scores = {}
    
    # Merge custom colloquial slangs / regional expressions for higher accuracy (Indian context)
    colloquial_keywords = {
        "bhai": "funny", "yaar": "funny", "hehe": "funny", "haha": "funny",
        "xd": "funny", "rofl": "funny", "lmfao": "funny", "kidding": "funny",
        "op": "fire", "mast": "fire", "gazab": "fire", "solid": "fire",
        "dhamaal": "fire", "bawal": "fire", "awesome": "fire", "bro": "funny",
        "rona": "sad", "dukh": "sad", "dukkha": "sad", "sed": "sad",
        "dard": "sad", "crying": "sad", "pyar": "love", "pyaar": "love",
        "dil": "love", "dost": "friendship", "bestie": "friendship",
        "macha": "friendship", "party": "celebration", "wow": "shocking",
        "amazing": "talent", "mindblowing": "shocking", "cringe": "cringe"
    }
    all_keywords = {**KEYWORD_CATEGORIES, **colloquial_keywords}
    
    # Helper function to score text with a custom weight
    def score_text_keywords(text: str, weight: int):
        if not text:
            return
        text_lower = text.lower()
        for keyword, category in all_keywords.items():
            pattern = r'\b' + re.escape(keyword) + r'\b'
            matches = len(re.findall(pattern, text_lower))
            if matches > 0:
                category_scores[category] = category_scores.get(category, 0) + (matches * weight)

    # Score companion message (high weight: 3)
    if message_text:
        score_text_keywords(message_text, 3)
        
    # Score reel caption and comments (standard weight: 1)
    if caption_text:
        score_text_keywords(caption_text, 1)
    for comment in comments:
        score_text_keywords(comment, 1)

    # 4. Score by found emojis (weighted higher, +6 for companion message, +2 for reel/comments)
    for emoji in found_message_emojis:
        category = EMOJI_TO_CATEGORY.get(emoji)
        if category:
            category_scores[category] = category_scores.get(category, 0) + 6
            
    for emoji in found_emojis:
        category = EMOJI_TO_CATEGORY.get(emoji)
        if category:
            category_scores[category] = category_scores.get(category, 0) + 2

    # 5. If we have scored categories, choose the top one and pick a relevant emoji
    if category_scores:
        top_category = max(category_scores, key=category_scores.get)
        emoji_options = CATEGORY_EMOJIS.get(top_category, DEFAULT_EMOJIS)
        
        # Prioritize reacting with the most frequent emoji found in message or reel
        all_found = found_message_emojis + found_emojis
        category_emojis_found = [e for e in all_found if e in emoji_options]
        if category_emojis_found:
            return max(set(category_emojis_found), key=category_emojis_found.count)
        
        return random.choice(emoji_options)

    # 6. Fallback options if no category or emoji matched
    if use_random_fallback:
        return random.choice(fallback_emojis)
    else:
        return fallback_emojis[0]


def analyze_with_gemini(api_key: str, caption: str, comments: list, message_text: str = None) -> str:
    """
    Call Gemini API to analyze the Reel content and comments, returning a single emoji.
    """
    if not api_key:
        return None
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    comments_str = "\n".join(f"- {c}" for c in comments[:30])
    
    prompt = f"""
You are an expert social media assistant.
Analyze the Instagram Reel content described below (the caption, comments, and the companion direct message sent when sharing it), and select exactly ONE emoji that best represents the sentiment, vibe, and appropriate reaction to this reel.

Reel Caption:
{caption or 'No caption'}

Direct Message (context of sharing):
{message_text or 'No direct message text'}

Reel Comments (up to 30):
{comments_str or 'No comments'}

CRITICAL RULES:
1. You MUST output ONLY a single emoji character (for example: 😂, 🔥, ❤️, 😮, 😢, etc.).
2. Do NOT output any words, punctuation, explanations, markdown, or spaces.
3. The emoji MUST be from standard Unicode emojis.
"""
    
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Check standard Gemini response structure
        if "candidates" in data and len(data["candidates"]) > 0:
            candidate = data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"] and len(candidate["content"]["parts"]) > 0:
                text = candidate["content"]["parts"][0]["text"].strip()
                # Clean up any unexpected text
                text = text.replace("*", "").replace("`", "").strip()
                parts = text.split()
                if parts:
                    emoji_candidate = parts[0]
                    # Emojis can have multiple code points, but length should be short
                    if len(emoji_candidate) <= 8:
                        return emoji_candidate
                    else:
                        return emoji_candidate[0]
    except Exception as e:
        # Raise to let the caller handle logging/fallback
        raise e
        
    return None

