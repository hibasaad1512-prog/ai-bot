from __future__ import annotations
import re
from collections import Counter

SCRIPT_PATTERNS = {
    "ar": re.compile(r"[\u0600-\u06ff]"),
    "ru": re.compile(r"[\u0400-\u04ff]"),
    "uk": re.compile(r"[\u0400-\u04ff]"),
    "el": re.compile(r"[\u0370-\u03ff]"),
    "he": re.compile(r"[\u0590-\u05ff]"),
    "ja": re.compile(r"[\u3040-\u30ff]"),
    "ko": re.compile(r"[\uac00-\ud7af]"),
    "zh": re.compile(r"[\u4e00-\u9fff]"),
}

PATTERNS = {
    "moroccan_darija": re.compile(r"\b(wach|wa|khoya|chno|hadchi|safi|bghit|mzyan|3lach|fin|makayn|labas|zwin)\b|(?:واش|خويا|شنو|هادشي|صافي|بغيت|مزيان|علاش|فين|كاين|ماكاين|لاباس|زوين)", re.I),
    "algerian_darija": re.compile(r"\b(wesh|saha|kifach|wech|khouya|bezzaf|haya|winak|sahbi)\b|(?:واش|صحا|كيفاش|خويا|بزاف|وينك|صحبي)", re.I),
    "tunisian": re.compile(r"\b(chnowa|chnoua|barra|behi|ya3tik|sahbi|kifech|winou)\b|(?:شنوة|برا|باهي|يعطيك|صاحبي|كيفاش|وينو)", re.I),
    "egyptian": re.compile(r"\b(eh|leh|keda|aywa|ya3ni|ya basha|delwa2ty|fein|gamed)\b|(?:ايه|ليه|كده|أيوه|يعني|دلوقتي|فين|جامد)", re.I),
    "levantine": re.compile(r"\b(shu|shou|kif|kifak|ya zalameh|habibi|wallo|hek)\b|(?:شو|كيفك|يا زلمة|حبيبي|والو|هيك)", re.I),
    "gulf": re.compile(r"\b(shlon|shsalfah|wala|yalla|abgha|marra|shfeek|wein)\b|(?:شلون|وشالسالفة|يلا|أبغى|مرة|شفيك|وين)", re.I),
    "iraqi": re.compile(r"\b(shako|shaku|shino|chako|hessa|habibi|yaba)\b|(?:شكو|شنو|هسه|حبيبي|يابا)", re.I),
    "french": re.compile(r"\b(quoi|frère|mdr|ptdr|mais|avec|pourquoi|vas-y|wesh)\b", re.I),
    "english": re.compile(r"\b(the|what|bro|why|this|that|lol|crazy|nah|idk|lmao|lowkey|ngl)\b", re.I),
    "spanish": re.compile(r"\b(que|porque|bro|jaja|oye|esto|como|vale|tio|tía)\b", re.I),
    "portuguese": re.compile(r"\b(que|porque|mano|kkkk|isso|como|beleza|cara)\b", re.I),
    "german": re.compile(r"\b(was|warum|bro|digga|lol|doch|nicht|wie|alter)\b", re.I),
    "italian": re.compile(r"\b(cosa|perché|bro|ahah|come|dai|ragazzi|bella)\b", re.I),
    "turkish": re.compile(r"\b(ne|neden|kanka|abi|ya|çok|nasıl|lan)\b|(?:ş|ğ|ı|İ|ç|ö|ü)", re.I),
    "dutch": re.compile(r"\b(wat|waarom|bro|lekker|echt|hoe|gast)\b", re.I),
    "polish": re.compile(r"\b(co|czemu|brat|kurde|dobra|jak|lol)\b", re.I),
    "romanian": re.compile(r"\b(ce|de ce|frate|boss|bine|cum|lol)\b", re.I),
    "czech": re.compile(r"\b(co|proč|kámo|brácho|hele|jak|lol)\b", re.I),
    "slovak": re.compile(r"\b(čo|prečo|kamo|brácho|ako|dobre|lol)\b", re.I),
    "hungarian": re.compile(r"\b(mi|miért|tesó|haver|ez|hogy|jó|lol)\b", re.I),
    "swedish": re.compile(r"\b(vad|varför|bror|fan|sjukt|hur|lol)\b", re.I),
    "norwegian": re.compile(r"\b(hva|hvorfor|bror|fyfaen|sykt|hvordan|lol)\b", re.I),
    "danish": re.compile(r"\b(hvad|hvorfor|bror|fedt|sygt|hvordan|lol)\b", re.I),
    "finnish": re.compile(r"\b(mitä|miksi|veli|ihan|siisti|miten|lol)\b", re.I),
    "hindi": re.compile(r"\b(kya|kyun|bhai|yaar|acha|accha|kaise|lol)\b|(?:क्या|क्यों|भाई|यार|अच्छा|कैसे)", re.I),
    "urdu": re.compile(r"\b(kya|kyun|bhai|yaar|acha|kaise|lol)\b|(?:کیا|کیوں|بھائی|یار|اچھا|کیسے)", re.I),
    "indonesian": re.compile(r"\b(apa|kenapa|bro|wkwk|gimana|bang|anjir|nggak)\b", re.I),
    "malay": re.compile(r"\b(apa|kenapa|bro|haha|macam|bang|tak|lah)\b", re.I),
    "tagalog": re.compile(r"\b(ano|bakit|bro|haha|grabe|paano|lods|tol)\b", re.I),
}

class LanguageProfile:
    def __init__(self):
        self.language="unknown"; self.dialect="unknown"; self.formality=0.4; self.slang=0.0; self.code_switching=0.0
    def as_dict(self): return {k:getattr(self,k) for k in ("language","dialect","formality","slang","code_switching")}

def _script_language(text: str) -> str:
    counts = Counter()
    for lang, pat in SCRIPT_PATTERNS.items():
        n = len(pat.findall(text))
        if n: counts[lang] += n
    if not counts: return ""
    if "ar" in counts and counts["ar"] >= 5: return "ar"
    if "ja" in counts: return "ja"
    if "ko" in counts: return "ko"
    if "zh" in counts: return "zh"
    if "el" in counts: return "el"
    if "he" in counts: return "he"
    if "ru" in counts: return "ru"
    return counts.most_common(1)[0][0]

def detect(messages: list[str]) -> LanguageProfile:
    p=LanguageProfile(); text=" ".join(messages[-20:]).strip()
    if not text: return p
    scores = Counter()
    for dialect, pattern in PATTERNS.items():
        hits=len(pattern.findall(text))
        if hits: scores[dialect]=hits
    script=_script_language(text)
    if scores:
        best, hits = scores.most_common(1)[0]
        lang_map={"moroccan_darija":"ar","algerian_darija":"ar","tunisian":"ar","egyptian":"ar","levantine":"ar","gulf":"ar","iraqi":"ar"}
        p.language=lang_map.get(best,{"english":"en","french":"fr","spanish":"es","portuguese":"pt","german":"de","italian":"it","turkish":"tr","dutch":"nl","polish":"pl","romanian":"ro","czech":"cs","slovak":"sk","hungarian":"hu","swedish":"sv","norwegian":"no","danish":"da","finnish":"fi","hindi":"hi","urdu":"ur","indonesian":"id","malay":"ms","tagalog":"tl"}.get(best,best))
        p.dialect=best
        second = scores.most_common(2)
        p.code_switching=0.75 if len(second)>1 and second[1][1]>=1 else 0.0
    elif script:
        p.language=script
        p.dialect="script_detected"
    else:
        p.language="unknown"; p.dialect="unknown"
    slang_terms = re.findall(r"\b(lol|lmao|mdr|ptdr|bro|nah|idk|ngl|lowkey|wesh|safi|wallah|yalla|kkkk|wkwk|haha)\b", text, re.I)
    p.slang=min(1.0,len(slang_terms)*0.10)
    if re.search(r"[\u0600-\u06ff]", text) and re.search(r"\b(bro|lol|mdr|wesh|nah)\b",text,re.I): p.code_switching=max(p.code_switching,0.55)
    p.formality=max(0.0,min(1.0,0.72 - p.slang*0.55))
    return p
