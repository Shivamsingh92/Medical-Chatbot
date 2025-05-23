! pip install -q chromadb sentence-transformers openai clip-anytorch timm
! pip install -U -q bitsandbytes accelerate transformers

import torch
import clip
from PIL import Image
# from transformers import BlipProcessor, BlipForConditionalGeneration
from sentence_transformers import SentenceTransformer

# Load CLIP for image embeddings
device = "cuda" if torch.cuda.is_available() else "cpu"
clip_model, clip_preprocess = clip.load("ViT-B/32", device=device)

# Load SentenceTransformer for text embeddings
# text_embed_model = SentenceTransformer("all-MiniLM-L6-v2")

# Load BLIP for image captioning (helps add more context for retrieval)
# blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-large")
# blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-large").to(device)

# def get_text_embedding(text):
#     return text_embed_model.encode(text).tolist()
# def get_text_embedding(text):
#     text_tokens = clip.tokenize([text]).to(device)
#     with torch.no_grad():
#         text_embedding = clip_model.encode_text(text_tokens).cpu().numpy().flatten()
#     return text_embedding.tolist()

# def get_image_embedding(image_path):
#     image = Image.open(image_path).convert("RGB")
#     image = clip_preprocess(image).unsqueeze(0).to(device)
#     with torch.no_grad():
#         image_embedding = clip_model.encode_image(image).cpu().numpy().flatten()
#     return image_embedding.tolist()

text_image_model = SentenceTransformer("clip-ViT-B-32")
model = SentenceTransformer('distiluse-base-multilingual-cased-v2')


def get_text_embedding(text):
    return model.encode(text).tolist()


def get_image_embedding(image_path):
    image = Image.open(image_path).convert("RGB")
    return text_image_model.encode(image).tolist()

# def generate_image_caption(image_path):
#     image = Image.open(image_path).convert("RGB")
#     inputs = blip_processor(image, return_tensors="pt").to(device)
#     caption = blip_model.generate(**inputs)
#     return blip_processor.decode(caption[0], skip_special_tokens=True)


# len(get_text_embedding("image_10.jpeg"))

# generate_image_caption("image_10.jpeg")

# !rm -r ./chroma_db

# from chromadb.utils import embedding_functions

# class CustomEmbeddingFunction(embedding_functions.EmbeddingFunction):
#     def __call__(self, input):
#         return text_image_model.encode(input).tolist()

import chromadb

chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="skin_diseases",)

# Insert a dummy 512D embedding to set the correct dimension
dummy_embedding = [0.0] * 512  # A vector of 512 zeros

collection.add(
    ids=["dummy_id"],
    embeddings=[dummy_embedding],  # This forces the collection to use 512D
    metadatas=[{"name": "Dummy Entry", "description": "Placeholder"}]
)

def add_skin_disease(doc_id, disease_name, symptoms, image_path):
    text_desc = f"{disease_name}: {symptoms}"
    # image_caption = generate_image_caption(image_path)  # Generate automatic caption for image

    text_embedding = get_text_embedding(text_desc)
    # print(len(text_embedding))
    # image_embedding = get_image_embedding(image_path)
    image_embedding = get_image_embedding(image_path)
    # print(len(image_embedding))

    # Combine embeddings
    final_embedding = [(x + y) / 2 for x, y in zip(text_embedding, image_embedding)]
    # print(len(final_embedding))

    metadata = {"id": doc_id, "disease": disease_name, "symptoms": symptoms, "image_path": image_path}

    collection.add(ids=[doc_id], embeddings=[final_embedding], metadatas=[metadata])

import os

for disease in sorted(os.listdir("/content/data")):
    disease_images=sorted(os.listdir("/content/data/"+disease+"/images"))
    symptoms=open("/content/data/"+disease+f"/texts/{disease}_symptoms.txt").read()
    for j in range(len(disease_images)):
      add_skin_disease(f"{disease}_{j}", disease,symptoms,"/content/data/"+disease+"/images/"+disease_images[j])


collection.get(include=["embeddings"])

def search_skin_disease(query_text=None, query_image=None, top_k=5):
    if query_image:
        image_embedding = get_image_embedding(query_image)
        results = collection.query(image_embedding, n_results=top_k)
    elif query_text:
        text_embedding = get_text_embedding(query_text)
        results = collection.query(text_embedding, n_results=top_k)
    else:
        raise ValueError("Provide either an image or a text description.")

    return results["metadatas"]

# # Example Search
# retrieved_cases = search_skin_disease(query_image="image_11.jpeg")
# print(retrieved_cases)

import huggingface_hub
huggingface_hub.login("hf-token please")

from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers import BitsAndBytesConfig
import torch

model_name = "mistralai/Mistral-7B-Instruct-v0.3"

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_name)

# Enable 4-bit quantization to reduce memory usage
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,  # Use 4-bit precision to reduce GPU RAM usage
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,  # Improves precision
    bnb_4bit_quant_type="nf4"  # Optimized quantization
)

# Load model with quantization
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    quantization_config=bnb_config,
    device_map="auto"  # Automatically distributes to available GPU
)

print("Model loaded successfully!")



# Load Mistral 7B Instruct Model
# model_name = "mistralai/Mistral-7B-Instruct-v0.1"
# tokenizer = AutoTokenizer.from_pretrained(model_name)
# model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.float16,
#     device_map={"": "cpu"},  # Forces CPU execution
#     offload_folder="offload")

def generate_diagnosis(retrieved_cases, user_query):
    # context = "\n".join([f"Disease: {case['disease']}\nSymptoms: {case['symptoms']}" for case in retrieved_cases])
    context = "\n".join([
        f"Disease: {case[0]['disease']}\nSymptoms: {case[0]['symptoms']}"
        for case in retrieved_cases  # Accessing the metadata list
    ])

    prompt = f"""
    A user has uploaded an image of a skin condition and described their symptoms.
    Based on the following medical records, provide a possible diagnosis.

    Medical Cases:
    {context}

    User Query:
    {user_query}

    Analyze the context carefully to extract Remedies of the disease.
    If it can'nt be found out from the context,advice the pateint to consult with a dermatologist.
    Diagnosis and Recommendations:
    """

    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    outputs = model.generate(**inputs, max_length=500)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)




# Example usage
query_text = "I have got an itchy rash and blisters at the site of my skin "
retrieved_cases = search_skin_disease(query_text=query_text, query_image="/content/data/acne_due_to_medicine/images/image_10.jpeg")
diagnosis = generate_diagnosis(retrieved_cases, query_text)
print(diagnosis)
