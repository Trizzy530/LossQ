import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel


router = APIRouter()


class OnboardingVoiceRequest(BaseModel):
    first_name: Optional[str] = None
    language: Optional[str] = "auto"


# LOSSQ_ELEVENLABS_ONBOARDING_VOICE_ROUTE_V1
WELCOME_MESSAGES = {
    "auto": "Welcome, {first_name}. I’m LossQ, your underwriting intelligence assistant. I’ll help you set up your company profile so your reports, carrier packets, and loss run analysis feel ready from the start.",
    "en": "Welcome, {first_name}. I’m LossQ, your underwriting intelligence assistant. I’ll help you set up your company profile so your reports, carrier packets, and loss run analysis feel ready from the start.",
    "fr": "Bienvenue, {first_name}. Je suis LossQ, votre assistant d’intelligence de souscription. Je vais vous aider à configurer votre profil d’entreprise afin que vos rapports, dossiers assureur et analyses de sinistres soient prêts dès le départ.",
    "es": "Bienvenido, {first_name}. Soy LossQ, tu asistente de inteligencia de suscripción. Te ayudaré a configurar el perfil de tu empresa para que tus reportes, paquetes para aseguradoras y análisis de siniestros estén listos desde el inicio.",
    "pt": "Bem-vindo, {first_name}. Eu sou a LossQ, sua assistente de inteligência de subscrição. Vou ajudar você a configurar o perfil da empresa para que relatórios, pacotes para seguradoras e análises de sinistros estejam prontos desde o início.",
    "de": "Willkommen, {first_name}. Ich bin LossQ, Ihre Assistentin für Underwriting-Intelligence. Ich helfe Ihnen, Ihr Unternehmensprofil einzurichten, damit Berichte, Carrier-Pakete und Schadenanalysen von Anfang an bereit sind.",
    "it": "Benvenuto, {first_name}. Sono LossQ, la tua assistente di intelligence assicurativa. Ti aiuterò a configurare il profilo aziendale in modo che report, pacchetti per le compagnie e analisi dei sinistri siano pronti fin dall’inizio.",
    "nl": "Welkom, {first_name}. Ik ben LossQ, uw underwriting intelligence-assistent. Ik help u uw bedrijfsprofiel in te stellen zodat rapporten, carrier-pakketten en schadeanalyses vanaf het begin klaar zijn.",
    "ar": "مرحباً، {first_name}. أنا LossQ، مساعدتك الذكية للاكتتاب التأميني. سأساعدك على إعداد ملف شركتك حتى تكون التقارير وملفات شركات التأمين وتحليل المطالبات جاهزة من البداية.",
    "zh": "欢迎，{first_name}。我是 LossQ，您的承保智能助手。我会帮助您设置公司资料，让报告、承保资料包和赔付记录分析从一开始就准备就绪。",
    "ja": "ようこそ、{first_name}。私は LossQ、引受インテリジェンスアシスタントです。会社プロフィールを設定し、レポート、保険会社向け資料、損害分析を最初から整えられるようお手伝いします。",
    "ko": "환영합니다, {first_name}. 저는 LossQ, 언더라이팅 인텔리전스 어시스턴트입니다. 회사 프로필을 설정해 보고서, 보험사 제출 자료, 손해 분석이 처음부터 준비되도록 도와드리겠습니다.",
    "hi": "स्वागत है, {first_name}. मैं LossQ हूँ, आपकी अंडरराइटिंग इंटेलिजेंस सहायक। मैं आपकी कंपनी प्रोफ़ाइल सेट करने में मदद करूँगी ताकि रिपोर्ट, कैरियर पैकेट और लॉस रन विश्लेषण शुरुआत से तैयार रहें.",
    "pa": "ਸਵਾਗਤ ਹੈ, {first_name}. ਮੈਂ LossQ ਹਾਂ, ਤੁਹਾਡੀ ਅੰਡਰਰਾਈਟਿੰਗ ਇੰਟੈਲੀਜੈਂਸ ਸਹਾਇਕ। ਮੈਂ ਤੁਹਾਡੀ ਕੰਪਨੀ ਪ੍ਰੋਫਾਈਲ ਸੈੱਟ ਕਰਨ ਵਿੱਚ ਮਦਦ ਕਰਾਂਗੀ ਤਾਂ ਜੋ ਰਿਪੋਰਟਾਂ, ਕੈਰੀਅਰ ਪੈਕੇਟ ਅਤੇ ਲਾਸ ਰਨ ਵਿਸ਼ਲੇਸ਼ਣ ਸ਼ੁਰੂ ਤੋਂ ਤਿਆਰ ਹੋਣ.",
    "ur": "خوش آمدید، {first_name}. میں LossQ ہوں، آپ کی انڈر رائٹنگ انٹیلیجنس اسسٹنٹ۔ میں آپ کی کمپنی پروفائل سیٹ کرنے میں مدد کروں گی تاکہ رپورٹس، کیریئر پیکٹس اور لاس رن تجزیہ شروع سے تیار ہوں.",
    "vi": "Chào mừng, {first_name}. Tôi là LossQ, trợ lý trí tuệ underwriting của bạn. Tôi sẽ giúp bạn thiết lập hồ sơ công ty để báo cáo, bộ hồ sơ gửi hãng bảo hiểm và phân tích loss run sẵn sàng ngay từ đầu.",
    "tl": "Welcome, {first_name}. Ako si LossQ, ang iyong underwriting intelligence assistant. Tutulungan kitang i-set up ang company profile para handa agad ang reports, carrier packets, at loss run analysis.",
    "pl": "Witamy, {first_name}. Jestem LossQ, Twoją asystentką do inteligentnej analizy underwritingowej. Pomogę skonfigurować profil firmy, aby raporty, pakiety dla ubezpieczycieli i analizy szkód były gotowe od początku.",
    "ru": "Добро пожаловать, {first_name}. Я LossQ, ваш помощник по андеррайтинговой аналитике. Я помогу настроить профиль компании, чтобы отчёты, пакеты для страховщиков и анализ убытков были готовы с самого начала.",
    "uk": "Ласкаво просимо, {first_name}. Я LossQ, ваш помічник з андеррайтингової аналітики. Я допоможу налаштувати профіль компанії, щоб звіти, пакети для страховиків і аналіз збитків були готові з самого початку.",
    "el": "Καλώς ήρθατε, {first_name}. Είμαι η LossQ, η βοηθός σας για underwriting intelligence. Θα σας βοηθήσω να ρυθμίσετε το εταιρικό προφίλ ώστε οι αναφορές, τα πακέτα ασφαλιστών και η ανάλυση ζημιών να είναι έτοιμα από την αρχή.",
    "tr": "Hoş geldiniz, {first_name}. Ben LossQ, underwriting intelligence asistanınız. Şirket profilinizi ayarlamanıza yardımcı olacağım; böylece raporlar, sigorta şirketi paketleri ve hasar analizleri en baştan hazır olur.",
    "he": "ברוך הבא, {first_name}. אני LossQ, עוזרת מודיעין החיתום שלך. אעזור לך להגדיר את פרופיל החברה כדי שהדוחות, תיקי המבטחים וניתוח התביעות יהיו מוכנים מההתחלה.",
    "sw": "Karibu, {first_name}. Mimi ni LossQ, msaidizi wako wa akili ya underwriting. Nitakusaidia kuweka wasifu wa kampuni ili ripoti, vifurushi vya wabeba bima, na uchambuzi wa madai viwe tayari tangu mwanzo.",
}


def lossq_safe_first_name(value: Optional[str]) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\r\n<>`{}[\]\\]", "", text)
    first = text.split(" ")[0].strip() if text else ""
    return first[:40] or "there"


def lossq_language_key(value: Optional[str]) -> str:
    key = str(value or "auto").strip().lower()
    key = key.split("-")[0]
    return key if key in WELCOME_MESSAGES else "auto"


@router.post("/onboarding-welcome")
def onboarding_welcome(payload: OnboardingVoiceRequest):
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    model_id = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip() or "eleven_multilingual_v2"

    if not api_key or not voice_id:
        raise HTTPException(status_code=503, detail="ElevenLabs voice is not configured.")

    first_name = lossq_safe_first_name(payload.first_name)
    language = lossq_language_key(payload.language)
    text = WELCOME_MESSAGES.get(language, WELCOME_MESSAGES["auto"]).format(first_name=first_name)

    body = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.62,
            "similarity_boost": 0.82,
            "style": 0.18,
            "use_speaker_boost": True,
        },
    }

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"

    request = urllib.request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(status_code=502, detail=f"ElevenLabs voice request failed: {detail}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Voice generation failed: {str(exc)[:300]}") from exc

    if not audio:
        raise HTTPException(status_code=502, detail="ElevenLabs returned empty audio.")

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-LossQ-Voice-Provider": "elevenlabs",
        },
    )
