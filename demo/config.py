
# ==========================================
# PROVIDERS CONFIG
# ==========================================
PROVIDERS = {
    "Scaleway": {
        "base_url": "https://api.scaleway.ai/v1",
        "key_name": "SCALEWAY",
        "badge": "🇫🇷 <b>DSGVO-Konform</b>",
        "chat_models": [
            "gpt-oss-120b", 
            "mistral-small-3.2-24b-instruct-2506", 
            "gemma-3-27b-it", 
            "qwen3-235b-a22b-instruct-2507", 
            "llama-3.3-70b-instruct", 
            "deepseek-r1-distill-llama-70b"
        ],
        "vision_models": ["pixtral-12b-2409", "mistral-small-3.1-24b-instruct-2503"],
        "audio_models": ["whisper-large-v3"],
        "image_models": ["pixtral-12b-2409"],
        "context_limits": {
            "gpt-oss-120b": 32768,
            "mistral-small-3.2-24b-instruct-2506": 32768,
            "gemma-3-27b-it": 96000,
            "qwen3-235b-a22b-instruct-2507": 131072,
            "llama-3.3-70b-instruct": 131072,
            "deepseek-r1-distill-llama-70b": 8192,
            "pixtral-12b-2409": 32768,
            "mistral-small-3.1-24b-instruct-2503": 96000,
            "whisper-large-v3": 16384,
        }
    },
    
    "Gladia": {
        "base_url": "https://api.gladia.io/v2",
        "key_name": "GLADIA",
        "badge": "🇫🇷 <b>DSGVO-Konform</b>",
        "audio_models": ["gladia-v2"],
        "context_limits": {
            "gladia-v2": 1000000 
        }
    },
    
    "Nebius": {
        "base_url": "https://api.tokenfactory.nebius.com/v1",
        "key_name": "NEBIUS",
        "badge": "🇪🇺 <b>DSGVO-Konform</b>",
        "chat_models": [
            "deepseek-ai/DeepSeek-R1-0528",
            "nvidia/Llama-3_1-Nemotron-Ultra-253B-v1",
            "openai/gpt-oss-120b",
            "moonshotai/Kimi-K2-Instruct",
            "moonshotai/Kimi-K2-Thinking",
            "zai-org/GLM-4.5",
            "meta-llama/Llama-3.3-70B-Instruct"
        ],
        "image_models": ["black-forest-labs/flux-schnell", "black-forest-labs/flux-dev"],
        "vision_models": ["google/gemma-3-27b-it", "Qwen/Qwen2.5-VL-72B-Instruct", "nvidia/Nemotron-Nano-V2-12b"],
        "context_limits": {
            "deepseek-ai/DeepSeek-R1-0528": 163840,
            "nvidia/Llama-3_1-Nemotron-Ultra-253B-v1": 131072,
            "openai/gpt-oss-120b": 32768,
            "moonshotai/Kimi-K2-Instruct": 128000,
            "moonshotai/Kimi-K2-Thinking": 128000,
            "zai-org/GLM-4.5": 128000,
            "meta-llama/Llama-3.3-70B-Instruct": 131072,
            "black-forest-labs/flux-schnell": 4096,
            "black-forest-labs/flux-dev": 4096,
        }
    },
    
    "Mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "key_name": "MISTRAL",
        "badge": "🇫🇷 <b>DSGVO-Konform</b>",
        "chat_models": [
            "mistral-large-latest",
            "mistral-medium-2508",
            "magistral-medium-2509",
            "open-mistral-nemo-2407"
        ],
        "vision_models": [
            "pixtral-large-latest", 
            # "pixtral-large-2411",
            "pixtral-12b-2409", 
            "mistral-ocr-latest",
            "mistral-large-latest",    # Mistral Large 3
            "mistral-medium-latest",   # Mistral Medium 3
            "mistral-small-latest",    # Mistral Small 3
            "ministral-14b-2512",
            "ministral-8b-2512"
        ],
        "audio_models": ["voxtral-mini-latest", "voxtral-mini-transcribe-realtime-2602"],
        "image_models": ["mistral-medium-2505"],
        "context_limits": {
            "mistral-large-latest": 128000,
            "mistral-medium-2508": 128000,
            "magistral-medium-2509": 128000,
            "open-mistral-nemo-2407": 128000,
            "pixtral-large-2411": 128000,
            "pixtral-12b-2409": 32768,
            "mistral-ocr-latest": 32768,
            "voxtral-mini-latest": 16384,
        }
    },
    
    "BFL": {
        "base_url": "https://api.bfl.ai/v1",
        "key_name": "BFL",
        "badge": "🇩🇪 <b>EU-Server & Firma</b>",
        "image_models": [
            "flux-pro-1.1", 
            "flux-pro-1.1-ultra", 
            "flux-2-max", 
            "flux-2-pro", 
            "flux-2-klein-4b", 
            "flux-2-klein-9b"
        ],
        "context_limits": {
             # Dummy limits for consistency
             "flux-pro-1.1": 4096, 
             "flux-pro-1.1-ultra": 4096, 
             "flux-2-max": 4096, 
             "flux-2-pro": 4096, 
             "flux-2-klein-4b": 4096, 
             "flux-2-klein-9b": 4096
        }
    },
    
    "Deepgram": {
        "base_url": "https://api.eu.deepgram.com/v1",
        "key_name": "DEEPGRAM",
        "badge": "🇪🇺 <b>EU-Server, US-Firma</b>",
        "audio_models": ["nova-3-general", "nova-2-general", "nova-2"],
        "context_limits": {
            "nova-3-general": 16384,
            "nova-2-general": 16384,
            "nova-2": 16384,
        }
    },
    
    "AssemblyAI": {
        "base_url": "https://api.eu.assemblyai.com/v2",
        "key_name": "ASSEMBLYAI",
        "badge": "🇪🇺 <b>EU-Server, US-Firma</b>",
        "audio_models": ["universal", "slam-1"],
        "context_limits": {
            "universal": 16384,
            "slam-1": 16384,
        }
    },
    
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_name": "OPENROUTER",
        "badge": "🇺🇸 <b>US-Server</b>!",
        "chat_models": [
            # 1M+ Context
            "google/gemini-2.0-pro-exp-02-05:free",
            "google/gemini-2.0-flash-thinking-exp:free",
            "google/gemini-2.0-flash-exp:free",
            "google/gemini-2.5-pro-exp-03-25:free",
            "google/gemini-flash-1.5-8b-exp",
            # 100K+ Context
            "deepseek/deepseek-r1-zero:free",
            "deepseek/deepseek-r1:free",
            "deepseek/deepseek-v3-base:free",
            "deepseek/deepseek-chat-v3-0324:free",
            "deepseek/deepseek-chat:free",
            "google/gemma-3-4b-it:free",
            "google/gemma-3-12b-it:free",
            "qwen/qwen2.5-vl-72b-instruct:free",
            "nvidia/llama-3.1-nemotron-70b-instruct:free",
            "meta-llama/llama-3.2-1b-instruct:free",
            "meta-llama/llama-3.2-11b-vision-instruct:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-nemo:free",
            # 64K-100K Context
            "mistralai/mistral-small-3.1-24b-instruct:free",
            "google/gemma-3-27b-it:free",
            "qwen/qwen2.5-vl-3b-instruct:free",
            "qwen/qwen-2.5-vl-7b-instruct:free",
            # 32K-64K Context
            "google/learnlm-1.5-pro-experimental:free",
            "qwen/qwq-32b:free",
            "google/gemini-2.0-flash-thinking-exp-1219:free",
            "bytedance-research/ui-tars-72b:free",
            "google/gemma-3-1b-it:free",
            "mistralai/mistral-small-24b-instruct-2501:free",
            "qwen/qwen-2.5-coder-32b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free",
            # 8K-32K Context
            "meta-llama/llama-3.2-3b-instruct:free",
            "qwen/qwq-32b-preview:free",
            "deepseek/deepseek-r1-distill-qwen-32b:free",
            "qwen/qwen2.5-vl-32b-instruct:free",
            "deepseek/deepseek-r1-distill-llama-70b:free",
            "qwen/qwen-2-7b-instruct:free",
            "google/gemma-2-9b-it:free",
            "mistralai/mistral-7b-instruct:free",
            "microsoft/phi-3-mini-128k-instruct:free",
            "meta-llama/llama-3-8b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            # 4K Context
            "huggingfaceh4/zephyr-7b-beta:free",
        ],
        "vision_models": [
            "google/gemini-2.0-pro-exp-02-05:free",
            "google/gemini-2.0-flash-thinking-exp:free",
            "google/gemini-2.0-flash-exp:free",
            "google/gemini-2.5-pro-exp-03-25:free",
            "google/gemini-flash-1.5-8b-exp",
            "qwen/qwen2.5-vl-72b-instruct:free",
            "meta-llama/llama-3.2-11b-vision-instruct:free",
            "mistralai/mistral-small-3.1-24b-instruct:free",
            "google/gemma-3-27b-it:free",
            "qwen/qwen2.5-vl-3b-instruct:free",
            "qwen/qwen-2.5-vl-7b-instruct:free",
            "bytedance-research/ui-tars-72b:free",
            "qwen/qwen2.5-vl-32b-instruct:free",
        ],
        "audio_models": [
            "google/gemini-2.0-flash-lite-001",
            "mistralai/voxtral-small-24b-2507",
            "google/gemini-2.5-flash-lite"
        ],
        "image_models": [
            "google/gemini-2.5-flash-image",
            "openai/gpt-5-image-mini",
            "google/gemini-3-pro-image-preview",
            "black-forest-labs/flux.2-pro",
            "black-forest-labs/flux.2-flex"
        ],
        "context_limits": {
            # 1M+ Context
            "google/gemini-2.0-pro-exp-02-05:free": 2000000,
            "google/gemini-2.0-flash-thinking-exp:free": 1048576,
            "google/gemini-2.0-flash-exp:free": 1048576,
            "google/gemini-2.5-pro-exp-03-25:free": 1000000,
            "google/gemini-flash-1.5-8b-exp": 1000000,
            # 100K+ Context
            "deepseek/deepseek-r1-zero:free": 163840,
            "deepseek/deepseek-r1:free": 163840,
            "deepseek/deepseek-v3-base:free": 131072,
            "deepseek/deepseek-chat-v3-0324:free": 131072,
            "deepseek/deepseek-chat:free": 131072,
            "google/gemma-3-4b-it:free": 131072,
            "google/gemma-3-12b-it:free": 131072,
            "qwen/qwen2.5-vl-72b-instruct:free": 131072,
            "nvidia/llama-3.1-nemotron-70b-instruct:free": 131072,
            "meta-llama/llama-3.2-1b-instruct:free": 131072,
            "meta-llama/llama-3.2-11b-vision-instruct:free": 131072,
            "meta-llama/llama-3.1-8b-instruct:free": 131072,
            "mistralai/mistral-nemo:free": 128000,
            # 64K-100K Context
            "mistralai/mistral-small-3.1-24b-instruct:free": 96000,
            "google/gemma-3-27b-it:free": 96000,
            "qwen/qwen2.5-vl-3b-instruct:free": 64000,
            "qwen/qwen-2.5-vl-7b-instruct:free": 64000,
            # 32K-64K Context
            "google/learnlm-1.5-pro-experimental:free": 40960,
            "qwen/qwq-32b:free": 40000,
            "google/gemini-2.0-flash-thinking-exp-1219:free": 40000,
            "bytedance-research/ui-tars-72b:free": 32768,
            "google/gemma-3-1b-it:free": 32768,
            "mistralai/mistral-small-24b-instruct-2501:free": 32768,
            "qwen/qwen-2.5-coder-32b-instruct:free": 32768,
            "qwen/qwen-2.5-72b-instruct:free": 32768,
            # 8K-32K Context
            "meta-llama/llama-3.2-3b-instruct:free": 20000,
            "qwen/qwq-32b-preview:free": 16384,
            "deepseek/deepseek-r1-distill-qwen-32b:free": 16000,
            "qwen/qwen2.5-vl-32b-instruct:free": 8192,
            "deepseek/deepseek-r1-distill-llama-70b:free": 8192,
            "qwen/qwen-2-7b-instruct:free": 8192,
            "google/gemma-2-9b-it:free": 8192,
            "mistralai/mistral-7b-instruct:free": 8192,
            "microsoft/phi-3-mini-128k-instruct:free": 8192,
            "meta-llama/llama-3-8b-instruct:free": 8192,
            "meta-llama/llama-3.3-70b-instruct:free": 8000,
            # 4K Context
            "huggingfaceh4/zephyr-7b-beta:free": 4096,
            # Audio/Image
            "google/gemini-2.0-flash-lite-001": 1000000,
            "mistralai/voxtral-small-24b-2507": 32768,
            "google/gemini-2.5-flash-lite": 1000000,
            "google/gemini-2.5-flash-image": 1000000,
            "openai/gpt-5-image-mini": 128000,
            "google/gemini-3-pro-image-preview": 1000000,
            "black-forest-labs/flux.2-pro": 4096,
            "black-forest-labs/flux.2-flex": 4096,
        }
    },
    
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_name": "GROQ",
        "badge": "🇺🇸 <b>US-Server</b>",
        "chat_models": [
            # Production models (no prefix)
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            
            # Preview models (with prefixes)
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "openai/gpt-oss-safeguard-20b",
            "moonshotai/kimi-k2-instruct-0905",
            "moonshotai/kimi-k2-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-guard-4-12b",
            "meta-llama/llama-prompt-guard-2-22m",
            "meta-llama/llama-prompt-guard-2-86m",
            "qwen/qwen3-32b",
            "allam-2-7b",
            
            # Systems
            "groq/compound",
            "groq/compound-mini",
        ],
        "vision_models": [
            # Vision models - REQUIRE meta-llama/ prefix
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
        ],
        "audio_models": [
            "whisper-large-v3",
            "whisper-large-v3-turbo"
        ],
        "tts_models": [
            "canopylabs/orpheus-v1-english",
            "canopylabs/orpheus-arabic-saudi"
        ],
        "context_limits": {
            # Production 
            "llama-3.1-8b-instant": 131072,
            "llama-3.3-70b-versatile": 131072,
            
            # Preview LLMs 
            "openai/gpt-oss-120b": 131072,
            "openai/gpt-oss-20b": 131072,
            "openai/gpt-oss-safeguard-20b": 131072,
            "moonshotai/kimi-k2-instruct-0905": 262144,
            "moonshotai/kimi-k2-instruct": 131072,
            "meta-llama/llama-4-maverick-17b-128e-instruct": 131072,
            "meta-llama/llama-4-scout-17b-16e-instruct": 131072,
            "meta-llama/llama-guard-4-12b": 131072,
            "meta-llama/llama-prompt-guard-2-22m": 512,
            "meta-llama/llama-prompt-guard-2-86m": 512,
            "qwen/qwen3-32b": 131072,
            "allam-2-7b": 4096,
            
            # Systems 
            "groq/compound": 131072,
            "groq/compound-mini": 131072,
            
            # Audio 
            "whisper-large-v3": 448,
            "whisper-large-v3-turbo": 448,
            
            # TTS 
            "canopylabs/orpheus-v1-english": 4000,
            "canopylabs/orpheus-arabic-saudi": 4000,
        }
    },
    
    "Poe": {
        "base_url": "https://api.poe.com/v1",
        "key_name": "POE",
        "badge": "🌐 <b>US-Server</b>!",
        "chat_models": [
            "gpt-5.1-instant",
            "claude-sonnet-4.5",
            "gemini-3-pro",
            "gpt-5.1",
            "gpt-4o",
            "claude-3.5-sonnet",
            "deepseek-r1",
            "grok-4"
        ],
        "vision_models": [
            "claude-sonnet-4.5",
            "gpt-5.1",
            "gemini-3-pro",
            "gpt-4o",
            "claude-3.5-sonnet"
        ],
        "image_models": [
            "gpt-image-1",
            "flux-pro-1.1-ultra",
            "ideogram-v3",
            "dall-e-3",
            "playground-v3"
        ],
        "audio_models": [
            "elevenlabs-v3",
            "sonic-3.0"
        ],
        "video_models": [
            "kling-2.5-turbo-pro",
            "runway-gen-4-turbo",
            "veo-3.1"
        ],
        "supports_system": True,
        "supports_streaming": True,
        "context_limits": {
            "gpt-5.1-instant": 128000,
            "claude-sonnet-4.5": 200000,
            "gemini-3-pro": 2000000,
            "gpt-5.1": 128000,
            "gpt-4o": 128000,
            "claude-3.5-sonnet": 200000,
            "deepseek-r1": 163840,
            "grok-4": 131072,
            "gpt-image-1": 4096,
            "flux-pro-1.1-ultra": 4096,
            "ideogram-v3": 4096,
            "dall-e-3": 4096,
            "playground-v3": 4096,
            "elevenlabs-v3": 4096,
            "sonic-3.0": 4096,
            "kling-2.5-turbo-pro": 4096,
            "runway-gen-4-turbo": 4096,
            "veo-3.1": 4096,
        }
    },
    
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "key_name": "OPENAI",
        "badge": "🇺🇸 <b>US-Server</b>!",
        "chat_models": [
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-0125",
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-4o-mini",
            "o1-preview",
            "o1-mini"
        ],
        "vision_models": [
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-4o-mini",
            "o1-preview",
            "o1-mini"
        ],
        "context_limits": {
            "gpt-3.5-turbo": 16385,
            "gpt-3.5-turbo-0125": 16385,
            "gpt-3.5-turbo-instruct": 4096,
            "gpt-4": 8192,
            "gpt-4-turbo": 128000,
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "o1-preview": 128000,
            "o1-mini": 128000,
        }
    },
    
    "Cohere": {
        "base_url": "https://api.cohere.ai/v1",
        "key_name": "COHERE",
        "badge": "🇺🇸 <b>US-Server</b>!",
        "chat_models": [
            "command-r-plus-08-2024",
            "command-r-plus",
            "command-r-08-2024",
            "command-r",
            "command",
            "c4ai-aya-expanse-8b",
            "c4ai-aya-expanse-32b",
        ],
        "context_limits": {
            "command-r-plus-08-2024": 131072,
            "command-r-plus-04-2024": 131072,
            "command-r-plus": 131072,
            "command-r-08-2024": 131072,
            "command-r-03-2024": 131072,
            "command-r": 131072,
            "command": 4096,
            "command-nightly": 131072,
            "command-light": 4096,
            "command-light-nightly": 4096,
            "c4ai-aya-expanse-8b": 8192,
            "c4ai-aya-expanse-32b": 131072,
        }
    },
    
    "Together": {
        "base_url": "https://api.together.xyz/v1",
        "key_name": "TOGETHER",
        "badge": "🇺🇸 <b>US-Server</b>!",
        "chat_models": [
            "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
            "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        ],
        "vision_models": ["meta-llama/Llama-Vision-Free"],
        "context_limits": {
            "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": 131072,
            "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free": 8192,
            "meta-llama/Llama-Vision-Free": 8192,
            "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free": 8192,
        }
    },
    
    "OVH": {
        "base_url": "https://llama-3-1-70b-instruct.endpoints.kepler.ai.cloud.ovh.net/api/openai_compat/v1",
        "key_name": "OVH",
        "badge": "🇫🇷 <b>DSGVO-Konform</b>",
        "chat_models": [
            "ovh/codestral-mamba-7b-v0.1",
            "ovh/deepseek-r1-distill-llama-70b",
            "ovh/llama-3.1-70b-instruct",
            "ovh/llama-3.1-8b-instruct",
            "ovh/llama-3.3-70b-instruct",
            "ovh/mistral-7b-instruct-v0.3",
            "ovh/mistral-nemo-2407",
            "ovh/mixtral-8x7b-instruct",
            "ovh/qwen2.5-coder-32b-instruct",
        ],
        "vision_models": [
            "ovh/llava-next-mistral-7b",
            "ovh/qwen2.5-vl-72b-instruct"
        ],
        "context_limits": {
            "ovh/codestral-mamba-7b-v0.1": 131072,
            "ovh/deepseek-r1-distill-llama-70b": 8192,
            "ovh/llama-3.1-70b-instruct": 131072,
            "ovh/llama-3.1-8b-instruct": 131072,
            "ovh/llama-3.3-70b-instruct": 131072,
            "ovh/llava-next-mistral-7b": 8192,
            "ovh/mistral-7b-instruct-v0.3": 32768,
            "ovh/mistral-nemo-2407": 131072,
            "ovh/mixtral-8x7b-instruct": 32768,
            "ovh/qwen2.5-coder-32b-instruct": 32768,
            "ovh/qwen2.5-vl-72b-instruct": 131072,
        }
    },
    
    "Cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "key_name": "CEREBRAS",
        "badge": "🇺🇸 <b>US-Server</b>!",
        "chat_models": [
            "llama3.1-8b",
            "llama-3.3-70b"
        ],
        "context_limits": {
            "llama3.1-8b": 8192,
            "llama-3.3-70b": 8192,
        }
    },
    
    "GoogleAI": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "key_name": "GOOGLEAI",
        "badge": "🇺🇸 <b>US-Server</b>?",
        "chat_models": [
            "gemini-1.0-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-pro",
            "gemini-2.5-pro"
        ],
        "vision_models": [
            "gemini-1.5-pro",
            "gemini-1.0-pro",
            "gemini-1.5-flash",
            "gemini-2.0-pro",
            "gemini-2.5-pro"
        ],
        "context_limits": {
            "gemini-1.0-pro": 32768,
            "gemini-1.5-flash": 1000000,
            "gemini-1.5-pro": 1000000,
            "gemini-2.0-pro": 2000000,
            "gemini-2.5-pro": 2000000,
        }
    },
    
    "Anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "key_name": "ANTHROPIC",
        "badge": "🇺🇸 <b>US-Server</b>!",
        "chat_models": [
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20240307",
            "claude-3-opus-20240229",
        ],
        "vision_models": [
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20240307",
            "claude-3-opus-20240229",
        ],
        "context_limits": {
            "claude-3-7-sonnet-20250219": 128000,
            "claude-3-5-sonnet-20241022": 200000,
            "claude-3-5-haiku-20240307": 200000,
            "claude-3-5-sonnet-20240620": 200000,
            "claude-3-opus-20240229": 200000,
            "claude-3-haiku-20240307": 200000,
            "claude-3-sonnet-20240229": 200000,
        }
    },
    
    "HuggingFace": {
        "base_url": "https://api-inference.huggingface.co/models",
        "key_name": "HUGGINGFACE",
        "badge": "🌐 <b>US-Server</b>?",
        "chat_models": [
            "microsoft/phi-3-mini-4k-instruct",
            "microsoft/Phi-3-mini-128k-instruct",
            "HuggingFaceH4/zephyr-7b-beta",
            "deepseek-ai/DeepSeek-Coder-V2-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
            "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
            "microsoft/Phi-3.5-mini-instruct",
            "google/gemma-2-2b-it",
            "Qwen/Qwen2.5-7B-Instruct",
            "tiiuae/falcon-7b-instruct",
            "Qwen/QwQ-32B-preview",
        ],
        "vision_models": [
            "Qwen/Qwen2.5-VL-7B-Instruct",
            "Qwen/qwen2.5-vl-3b-instruct",
            "Qwen/qwen2.5-vl-32b-instruct",
            "Qwen/qwen2.5-vl-72b-instruct",
        ],
        "context_limits": {
            "microsoft/phi-3-mini-4k-instruct": 4096,
            "microsoft/Phi-3-mini-128k-instruct": 131072,
            "HuggingFaceH4/zephyr-7b-beta": 8192,
            "deepseek-ai/DeepSeek-Coder-V2-Instruct": 8192,
            "mistralai/Mistral-7B-Instruct-v0.3": 32768,
            "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO": 32768,
            "microsoft/Phi-3.5-mini-instruct": 4096,
            "google/gemma-2-2b-it": 2048,
            "openai-community/gpt2": 1024,
            "microsoft/phi-2": 2048,
            "TinyLlama/TinyLlama-1.1B-Chat-v1.0": 2048,
            "Qwen/Qwen2.5-7B-Instruct": 131072,
            "tiiuae/falcon-7b-instruct": 8192,
            "Qwen/QwQ-32B-preview": 32768,
            "Qwen/Qwen2.5-VL-7B-Instruct": 64000,
            "Qwen/qwen2.5-vl-3b-instruct": 64000,
            "Qwen/qwen2.5-vl-32b-instruct": 8192,
            "Qwen/qwen2.5-vl-72b-instruct": 131072,
        }
    },

    "Requesty": {
        # EU router endpoint – always use this, never the US endpoint
        "base_url": "https://router.eu.requesty.ai/v1",
        "key_name": "REQUESTY",
        "badge": "🇪🇺 <b>EU-Router (gefiltert)</b>",
        # Curated EU-routed chat models (provider/model@region format).
        # All of these route through EU infrastructure verified via the /models API.
        "chat_models": [
            # Nebius (Netherlands) – EU-native
            "nebius/deepseek-ai/DeepSeek-V3.2",
            "nebius/deepseek-ai/DeepSeek-R1-0528",
            "nebius/moonshotai/kimi-k2.5",
            "nebius/Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "nebius/meta-llama/Llama-3.3-70B-Instruct",
            # Mistral (France) – EU-native
            "mistral/mistral-large-latest",
            "mistral/mistral-medium-latest",
            "mistral/devstral-latest",
            # AWS Bedrock – EU regions only
            "bedrock/claude-sonnet-4-6@eu-west-1",
            "bedrock/claude-sonnet-4-6@eu-central-1",
            "bedrock/claude-opus-4-5@eu-west-1",
            "bedrock/claude-opus-4-5@eu-central-1",
            "bedrock/claude-haiku-4-5@eu-west-1",
            # Google Vertex – EU regions only
            "vertex/gemini-2.5-pro@europe-west4",
            "vertex/gemini-2.5-pro@europe-west1",
            "vertex/gemini-2.5-flash@europe-west4",
            "vertex/gemini-2.5-flash@europe-west1",
            # Azure – EU regions only
            "azure/gpt-5.1@swedencentral",
            "azure/gpt-5.1@francecentral",
            "azure/gpt-4.1@swedencentral",
            "azure/gpt-4.1@francecentral",
            "azure/gpt-4.1-mini@swedencentral",
        ],
        "context_limits": {
            "nebius/deepseek-ai/DeepSeek-V3.2": 163840,
            "nebius/deepseek-ai/DeepSeek-R1-0528": 163840,
            "nebius/moonshotai/kimi-k2.5": 262144,
            "nebius/Qwen/Qwen3-Coder-480B-A35B-Instruct": 262144,
            "nebius/meta-llama/Llama-3.3-70B-Instruct": 131072,
            "mistral/mistral-large-latest": 131072,
            "mistral/mistral-medium-latest": 131072,
            "mistral/devstral-latest": 262144,
            "bedrock/claude-sonnet-4-6@eu-west-1": 1000000,
            "bedrock/claude-sonnet-4-6@eu-central-1": 1000000,
            "bedrock/claude-opus-4-5@eu-west-1": 200000,
            "bedrock/claude-opus-4-5@eu-central-1": 200000,
            "bedrock/claude-haiku-4-5@eu-west-1": 200000,
            "vertex/gemini-2.5-pro@europe-west4": 1000000,
            "vertex/gemini-2.5-pro@europe-west1": 1000000,
            "vertex/gemini-2.5-flash@europe-west4": 1000000,
            "vertex/gemini-2.5-flash@europe-west1": 1000000,
            "azure/gpt-5.1@swedencentral": 200000,
            "azure/gpt-5.1@francecentral": 200000,
            "azure/gpt-4.1@swedencentral": 1000000,
            "azure/gpt-4.1@francecentral": 1000000,
            "azure/gpt-4.1-mini@swedencentral": 1000000,
        },
    },

    "Langdock": {
        # German company (Hamburg), GDPR-compliant, EU Azure infrastructure.
        # OpenAI-compatible endpoint — drop-in for openai.OpenAI(base_url=...).
        "base_url": "https://api.langdock.com/openai/eu/v1",
        "key_name": "LANGDOCK",
        "badge": "🇩🇪 <b>DSGVO-Konform (EU-Azure)</b>",
        "chat_models": [
            # Flagship / latest
            "gpt-5",
            "gpt-5.1",
            "gpt-5.2",
            "gpt-5-mini",
            "gpt-5-nano",
            # Stable GPT-4 series
            "gpt-4o",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o-mini",
            # Reasoning models
            "o3",
            "o4-mini",
            "o1",
            "o3-mini",
            # Additional OpenAI models from live API
            "gpt-5.2-pro",
            "gpt-5.1-chat-latest",
            "gpt-5-chat-latest",
            # Anthropic models (via /anthropic/eu/v1/messages — native Anthropic format)
            "claude-sonnet-4-6-default",
            "claude-opus-4-6-default",
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-5-20251101",
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20240620",
            # Google Gemini models (via /google/eu/v1beta — native Vertex format)
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ],
        "context_limits": {
            # OpenAI
            "gpt-5":        400000,
            "gpt-5.1":      400000,
            "gpt-5.2":      400000,
            "gpt-5-mini":   200000,
            "gpt-5-nano":   200000,
            "gpt-4o":       128000,
            "gpt-4.1":      1000000,
            "gpt-4.1-mini": 1000000,
            "gpt-4.1-nano": 1000000,
            "gpt-4o-mini":  128000,
            "o3":           200000,
            "o4-mini":      200000,
            "o1":           200000,
            "o3-mini":      200000,
            # Anthropic
            "claude-sonnet-4-6-default":  200000,
            "claude-opus-4-6-default":    200000,
            "claude-sonnet-4-5-20250929": 200000,
            "claude-opus-4-5-20251101":   200000,
            "claude-haiku-4-5-20251001":  200000,
            "claude-sonnet-4-20250514":   200000,
            "claude-3-7-sonnet-20250219": 200000,
            "claude-3-5-sonnet-20240620": 200000,
            # Google
            "gemini-2.5-pro":   1000000,
            "gemini-2.5-flash":  1000000,
        },
    },
}

# ==========================================
# DEFAULTS
# ==========================================
DEFAULT_CHAT_PROVIDER = "Mistral"
DEFAULT_CHAT_MODEL = "mistral-large-latest"
                  