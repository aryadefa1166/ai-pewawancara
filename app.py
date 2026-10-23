import streamlit as st
from audio_recorder_streamlit import audio_recorder
from dotenv import load_dotenv
import os
import tempfile
import base64
from gtts import gTTS
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage
from groq import Groq

# 1. SETUP API & INISIALISASI
load_dotenv()
if not os.getenv("GROQ_API_KEY"):
    st.error("⚠️ API Key Groq belum ditemukan. Cek file .env Anda.")
    st.stop()

groq_api = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api)
llm = ChatGroq(model="openai/gpt-oss-20b", api_key=groq_api, temperature=0.7)

# 2. FUNGSI AUDIO (TEXT-TO-SPEECH)
@st.cache_data(show_spinner=False)
def get_tts_audio(text):
    tts = gTTS(text=text, lang='id')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        tts.save(fp.name)
        with open(fp.name, "rb") as f:
            data = f.read()
        os.remove(fp.name)
    return data

def autoplay_audio(audio_bytes):
    b64 = base64.b64encode(audio_bytes).decode()
    md = f'<audio autoplay="true" controls style="width: 100%;"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'
    st.markdown(md, unsafe_allow_html=True)

# 3. KONFIGURASI HALAMAN UTAMA
st.set_page_config(page_title="AI Pewawancara", page_icon="👔", layout="wide")
st.title("👔 Simulasi Sidang & Wawancara AI")
st.caption("AI akan berbicara langsung kepadamu. Balas menggunakan tombol rekam suara (Mic)!")

# 4. MEMORI PERCAKAPAN
if "messages" not in st.session_state:
    st.session_state.messages = [] 
if "display_messages" not in st.session_state:
    st.session_state.display_messages = [] 
if "sesi_aktif" not in st.session_state:
    st.session_state.sesi_aktif = False
if "jawaban_terproses" not in st.session_state:
    st.session_state.jawaban_terproses = None # Kunci untuk anti-looping

# 5. PANEL SAMPING (PENGATURAN)
with st.sidebar:
    st.header("⚙️ Pengaturan")
    posisi = st.text_input("Posisi / Topik:", placeholder="Contoh: AI Engineer")
    
    if st.button("Mulai Wawancara", type="primary"):
        if posisi:
            st.session_state.messages = []
            st.session_state.display_messages = []
            st.session_state.jawaban_terproses = None
            
            # SUNTIKAN PROMPT ENGINEERING (Santai & Keren)
            instruksi = (
                f"Bertindaklah sebagai pewawancara ahli bernama 'Ardan' (jika kamu memilih karakter pria) atau 'Kiara' (jika wanita). "
                f"Kamu sedang mengobrol santai lewat telepon dengan Aryadefa (mahasiswa Ilmu Komputer USU) untuk posisi: '{posisi}'. "
                f"Tugas: Sapa Aryadefa, perkenalkan dirimu, dan LANGSUNG BERIKAN 1 PERTANYAAN PERTAMA. "
                f"ATURAN: "
                f"1. JANGAN PERNAH menggunakan simbol markdown (*, #, []). "
                f"2. Gunakan gaya bahasa anak Jakarta/Startup yang asik, luwes, dan gak kaku. "
                f"3. Cukup berikan 1 pertanyaan per giliran."
            )
            st.session_state.messages.append(HumanMessage(content=instruksi))
            st.session_state.sesi_aktif = True
            
            with st.spinner("Menghubungkan panggilan..."):
                try:
                    response = llm.invoke(st.session_state.messages)
                    clean_text = response.content.replace("*", "").replace("#", "").replace("[", "").replace("]", "")
                    
                    st.session_state.messages.append(AIMessage(content=clean_text))
                    st.session_state.display_messages.append({"role": "assistant", "content": clean_text})
                except Exception as e:
                    st.error(f"Error LLM: {e}")
        else:
            st.warning("Isi dulu kolom Posisi / Topik!")

# 6. AREA CHAT UTAMA
if st.session_state.sesi_aktif:
    # Tampilkan histori
    for index, msg in enumerate(st.session_state.display_messages):
        avatar_icon = "👤" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar_icon):
            st.write(msg["content"])
            
            if msg["role"] == "assistant":
                audio_data = get_tts_audio(msg["content"])
                if index == len(st.session_state.display_messages) - 1:
                    autoplay_audio(audio_data)
                else:
                    st.audio(audio_data, format="audio/mp3")

    st.write("---")
    
    # Input Jawaban
    col1, col2 = st.columns([1, 4])
    jawaban_user = ""
    
    with col1:
        st.write("**Jawab pakai Mic:**")
        # key="audio_input" mencegah bentrok state
        audio_bytes = audio_recorder(text="Klik Mic", icon_size="2x", key="audio_input")
        if audio_bytes:
            # Cegah error audio terlalu pendek (minimal ~1000 bytes untuk rekaman suara beneran)
            if len(audio_bytes) > 2000:
                with st.spinner("Menerjemahkan suara..."):
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
                            temp_audio.write(audio_bytes)
                            temp_audio_path = temp_audio.name
                        with open(temp_audio_path, "rb") as file:
                            transcription = groq_client.audio.transcriptions.create(
                              file=(temp_audio_path, file.read()), model="whisper-large-v3", language="id"
                            )
                        jawaban_user = transcription.text
                        os.remove(temp_audio_path)
                    except Exception as e:
                        st.error(f"Gagal memproses suara: {e}")
            else:
                st.warning("Rekaman terlalu pendek, silakan tekan tahan dan bicara lebih jelas.")

    with col2:
        st.write("**Atau ketik teks:**")
        user_text = st.chat_input("Ketik jawaban di sini...")
        if user_text:
            jawaban_user = user_text

    # LOGIKA ANTI-LOOPING
    # Pastikan jawaban baru diproses jika berbeda dengan jawaban terakhir yang diproses
    if jawaban_user and jawaban_user != st.session_state.jawaban_terproses:
        
        # Simpan jawaban ini sebagai yang sedang diproses
        st.session_state.jawaban_terproses = jawaban_user
        
        prompt_pengingat = f"Jawaban Aryadefa: '{jawaban_user}'. (Ingat: Respons santai, asik, tanpa markdown, lalu lanjut 1 pertanyaan)."
        
        st.session_state.messages.append(HumanMessage(content=prompt_pengingat))
        st.session_state.display_messages.append({"role": "user", "content": jawaban_user})
        
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Mengevaluasi..."):
                try:
                    response = llm.invoke(st.session_state.messages)
                    clean_text = response.content.replace("*", "").replace("#", "").replace("[", "").replace("]", "")
                    
                    st.session_state.messages.append(AIMessage(content=clean_text))
                    st.session_state.display_messages.append({"role": "assistant", "content": clean_text})
                except Exception as e:
                    st.error(f"Error AI membalas: {e}")
        
        st.rerun() 
else:
    st.info("👈 Silakan ketik Posisi yang dilamar dan klik 'Mulai Wawancara'.")