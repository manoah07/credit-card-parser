import io
import json
import pdfplumber
import pytesseract
from PIL import Image
from openai import OpenAI
import os
from dotenv import load_dotenv

# Load environment variables (expects GROQ_API_KEY in .env)
load_dotenv()


class CreditCardParser:
    def __init__(self):
        self.groq_api_key = os.getenv('GROQ_API_KEY')
        if not self.groq_api_key:
            print("⚠️  Warning: GROQ_API_KEY not found in .env file")

    # ------------------------------------------------------------
    # 1. PDF → TEXT EXTRACTION with OCR fallback
    # ------------------------------------------------------------
    def extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF; if not found, fall back to OCR"""
        texts = []
        print(f"📄 Opening PDF: {pdf_path}")

        try:
            with pdfplumber.open(pdf_path) as pdf:
                print(f"   Total pages: {len(pdf.pages)}")

                for page_num, page in enumerate(pdf.pages, 1):
                    # Try normal text extraction
                    text = page.extract_text()

                    # OCR fallback for image-based pages
                    if not text or len(text.strip()) < 40:
                        print(f"   Page {page_num}: Using OCR fallback...")
                        try:
                            img = page.to_image(resolution=300).original
                            text = pytesseract.image_to_string(img)
                        except Exception as ocr_error:
                            print(f"   ⚠️ OCR failed: {ocr_error}")
                            text = ""
                    else:
                        print(f"   Page {page_num}: Extracted {len(text)} characters")

                    texts.append(text or "")

            full_text = "\n".join(texts)
            print(f"✅ Total extracted: {len(full_text)} characters\n")
            return full_text

        except Exception as e:
            print(f"❌ PDF extraction error: {e}")
            raise Exception(f"Error reading PDF: {str(e)}")

    # ------------------------------------------------------------
    # 2. Groq Llama-3.1 AI Query
    # ------------------------------------------------------------
    def query_groq(self, prompt):
        """Send extracted text to Groq’s Llama-3.1 model for parsing"""
        if not self.groq_api_key:
            raise Exception("GROQ_API_KEY not configured. Please add it to .env file.")

        print("🤖 Querying Groq AI (Llama-3.1-8B-Instant)...")

        try:
            client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=self.groq_api_key
            )

            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1024
            )

            response = completion.choices[0].message.content
            print(f"✅ AI Response received ({len(response)} chars)\n")
            return response

        except Exception as e:
            print(f"❌ Groq API Error: {e}")
            raise Exception(f"Groq API Error: {str(e)}")

    # ------------------------------------------------------------
    # 3. MAIN PARSE METHOD
    # ------------------------------------------------------------
    def parse(self, pdf_path):
        """Main parse pipeline: extract → analyze → JSONify"""
        try:
            print(f"\n{'='*60}")
            print(f"🚀 Starting AI-powered parsing")
            print(f"{'='*60}\n")

            # Step 1: Extract text
            pdf_text = self.extract_text_from_pdf(pdf_path)
            if not pdf_text.strip():
                return {'success': False, 'error': 'Could not extract text from PDF'}

            print("📝 Text sample (first 500 chars):")
            print(pdf_text[:500])
            print(f"\n{'='*60}\n")

            # Step 2: Build AI prompt
            prompt = f"""
You are an expert financial document parser.
Extract the following fields from this credit card statement:

1. issuer (bank name)
2. card_last4 (last 4 digits of card number)
3. statement_date (billing cycle or statement period)
4. due_date (payment due date)
5. total_balance (total amount due or outstanding balance)
6. minimum_payment (minimum payment amount)

Return ONLY a valid JSON object with these exact keys. No extra text.
If a field is missing, use "Not found" as its value.

Statement text:
{pdf_text[:7000]}
"""

            # Step 3: Query Groq AI
            response_text = self.query_groq(prompt)
            print("🔍 AI Raw Response:")
            print(response_text)
            print(f"\n{'='*60}\n")

            # Step 4: Extract JSON safely
            try:
                if '{' in response_text and '}' in response_text:
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1
                    json_str = response_text[json_start:json_end]
                    data = json.loads(json_str)
                else:
                    raise ValueError("No JSON object found in AI response")

                # Step 5: Infer issuer if missing
                if not data.get('issuer') or data['issuer'] == "Not found":
                    txt = pdf_text.lower()
                    if 'hsbc' in txt:
                        data['issuer'] = 'HSBC'
                    elif 'chase' in txt:
                        data['issuer'] = 'Chase'
                    elif 'amex' in txt or 'american express' in txt:
                        data['issuer'] = 'American Express'
                    elif 'citi' in txt:
                        data['issuer'] = 'Citi'
                    elif 'discover' in txt:
                        data['issuer'] = 'Discover'
                    elif 'capital one' in txt:
                        data['issuer'] = 'Capital One'
                    else:
                        data['issuer'] = 'Unknown'

                # Step 6: Cleanup numeric fields
                for key in ['total_balance', 'minimum_payment']:
                    if key in data and data[key] != "Not found":
                        data[key] = str(data[key]).replace('$', '').replace('₹', '').replace(',', '').strip()

                # Step 7: Compute success rate
                required = ['card_last4', 'statement_date', 'due_date', 'total_balance', 'minimum_payment']
                extracted = sum(1 for f in required if data.get(f) and data[f] != "Not found")
                success_rate = (extracted / len(required)) * 100

                print("✅ Final Extraction:")
                for k, v in data.items():
                    print(f"   {k}: {v}")
                print(f"\n📊 Success Rate: {extracted}/{len(required)} ({success_rate:.1f}%)")
                print(f"{'='*60}\n")

                return {
                    'success': True,
                    'data': data,
                    'extracted_fields': extracted,
                    'total_fields': len(required),
                    'success_rate': round(success_rate, 1),
                    'method': 'AI-Powered (Groq Llama-3.1)'
                }

            except json.JSONDecodeError as e:
                print(f"❌ JSON Parse Error: {e}")
                return {
                    'success': False,
                    'error': f'AI returned invalid JSON: {str(e)}',
                    'raw_response': response_text
                }

        except Exception as e:
            print(f"❌ Error: {e}")
            print(f"{'='*60}\n")
            return {'success': False, 'error': str(e)}
