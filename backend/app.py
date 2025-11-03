from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from parser import CreditCardParser
import os
from werkzeug.utils import secure_filename
import json
from datetime import datetime
import pandas as pd
from io import BytesIO

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
HISTORY_FILE = 'parse_history.json'
ALLOWED_EXTENSIONS = {'pdf'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    return []

def save_history(entry):
    history = load_history()
    history.insert(0, entry)
    history = history[:20]
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def generate_insights(data):
    """Generate AI-powered financial insights"""
    insights = []
    
    try:
        if 'total_balance' in data and 'minimum_payment' in data:
            try:
                balance = float(str(data['total_balance']).replace(',', '').replace('₹', '').replace('$', '').strip())
                min_payment = float(str(data['minimum_payment']).replace(',', '').replace('₹', '').replace('$', '').strip())
                
                if balance > 0 and min_payment > 0:
                    # High balance warning
                    if balance > 5000:
                        insights.append({
                            'type': 'warning',
                            'title': 'High Balance Alert',
                            'message': f'Balance of ₹{balance:,.2f} is significant. Consider paying more than minimum.',
                            'priority': 'high'
                        })
                    
                    # Minimum payment analysis
                    months_to_payoff = balance / min_payment if min_payment > 0 else 999
                    estimated_interest = balance * 0.18 * (months_to_payoff / 12)
                    
                    if months_to_payoff > 24:
                        insights.append({
                            'type': 'critical',
                            'title': 'Long Payoff Period',
                            'message': f'Paying minimum only will take {int(months_to_payoff)} months. Estimated interest: ₹{estimated_interest:,.2f}',
                            'priority': 'critical'
                        })
                    
                    # Savings recommendation
                    recommended_payment = balance / 12
                    if recommended_payment > min_payment:
                        savings = estimated_interest - (balance * 0.18 * 1)
                        if savings > 0:
                            insights.append({
                                'type': 'info',
                                'title': 'Smart Payment Tip',
                                'message': f'Pay ₹{recommended_payment:,.2f}/month to save ~₹{savings:,.2f} in interest',
                                'priority': 'medium'
                            })
            except (ValueError, TypeError) as e:
                print(f"Error calculating insights: {e}")
    
    except Exception as e:
        print(f"Error generating insights: {e}")
    
    return insights

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'message': 'API is running',
        'parser': 'AI-Powered (Groq Llama 3.1)'
    })

@app.route('/api/parse', methods=['POST'])
def parse_statement():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Only PDF files are allowed'}), 400
    
    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Parse with AI
        parser = CreditCardParser()
        result = parser.parse(filepath)
        
        if result['success']:
            # Add AI insights
            result['insights'] = generate_insights(result['data'])
            
            # Save to history
            history_entry = {
                'id': datetime.now().isoformat(),
                'filename': filename,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'result': result
            }
            save_history(history_entry)
        
        # Clean up uploaded file
        os.remove(filepath)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in parse endpoint: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    history = load_history()
    return jsonify({'success': True, 'history': history})

@app.route('/api/history', methods=['DELETE'])
def clear_history():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
    return jsonify({'success': True, 'message': 'History cleared'})

@app.route('/api/export/csv', methods=['POST'])
def export_csv():
    data = request.json
    
    try:
        df = pd.DataFrame([{
            'Issuer': data['data'].get('issuer', 'N/A'),
            'Card Last 4': data['data'].get('card_last4', 'N/A'),
            'Statement Date': data['data'].get('statement_date', 'N/A'),
            'Due Date': data['data'].get('due_date', 'N/A'),
            'Total Balance': data['data'].get('total_balance', 'N/A'),
            'Minimum Payment': data['data'].get('minimum_payment', 'N/A'),
        }])
        
        output = BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'statement_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/json', methods=['POST'])
def export_json():
    data = request.json
    
    try:
        output = BytesIO()
        output.write(json.dumps(data, indent=2).encode())
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name=f'statement_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/excel', methods=['POST'])
def export_excel():
    data = request.json
    
    try:
        df = pd.DataFrame([{
            'Issuer': data['data'].get('issuer', 'N/A'),
            'Card Last 4': data['data'].get('card_last4', 'N/A'),
            'Statement Date': data['data'].get('statement_date', 'N/A'),
            'Due Date': data['data'].get('due_date', 'N/A'),
            'Total Balance': data['data'].get('total_balance', 'N/A'),
            'Minimum Payment': data['data'].get('minimum_payment', 'N/A'),
        }])
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Statement')
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'statement_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    history = load_history()
    
    if not history:
        return jsonify({'success': False, 'error': 'No statements parsed yet'})
    
    try:
        total_parsed = len(history)
        issuers = {}
        total_balance = 0
        avg_success_rate = 0
        
        for entry in history:
            result = entry['result']
            if result['success']:
                issuer = result['data'].get('issuer', 'Unknown')
                issuers[issuer] = issuers.get(issuer, 0) + 1
                
                if 'total_balance' in result['data']:
                    try:
                        balance_str = str(result['data']['total_balance']).replace(',', '').replace('₹', '').replace('$', '').strip()
                        total_balance += float(balance_str)
                    except:
                        pass
                
                avg_success_rate += result.get('success_rate', 0)
        
        avg_success_rate = avg_success_rate / total_parsed if total_parsed > 0 else 0
        
        return jsonify({
            'success': True,
            'stats': {
                'total_parsed': total_parsed,
                'issuers_breakdown': issuers,
                'total_balance_parsed': round(total_balance, 2),
                'average_success_rate': round(avg_success_rate, 1)
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/supported-issuers', methods=['GET'])
def supported_issuers():
    issuers = ['HSBC', 'Chase', 'American Express', 'Citi', 'Discover', 'Capital One', 'Any Bank (AI-Powered)']
    return jsonify({'issuers': issuers})

import os

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🚀 Credit Card Parser API Starting...")
    print("=" * 70)
    print("🤖 Parser: AI-Powered (Groq Llama 3.1 8B Instant)")
    print("✨ Features:")
    print("   • AI-based extraction (works with any issuer)")
    print("   • OCR fallback for image-based PDFs")
    print("   • History tracking")
    print("   • Financial insights")
    print("   • Export to CSV/JSON/Excel")
    print("   • Statistics dashboard")
    print("=" * 70)
    print("\n⚠️  Make sure you have GROQ_API_KEY in .env file")
    print("   Get free API key: https://console.groq.com/keys\n")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
