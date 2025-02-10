import google.generativeai as genai
import os
import re
import pickle
import base64
import json
import time

from datetime import datetime
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.message import EmailMessage
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.utils import parsedate_to_datetime

# Escopo de autorização para acessar e modificar o Gmail
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/gmail.metadata',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]


os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

genai.configure(api_key="SUA CHAVE API")

# Configuração da API do Google
def get_gmail_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            print(creds.valid)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080)  # Porta fixa definida aqui
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    service = build('gmail', 'v1', credentials=creds)
    
    return service


# Função para limpar o texto do corpo do e-mail
def clean_email_body(body):
    # Remover tags HTML
    soup = BeautifulSoup(body, 'html.parser')
    clean_text = soup.get_text()

    # Remover URLs
    clean_text = re.sub(r'http\S+|www.\S+', '', clean_text)

    # Remover caracteres especiais e números
    clean_text = re.sub(r'[^A-Za-z\s]+', '', clean_text)

    # Remover múltiplos espaços
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    return clean_text


# Função para limpar o assunto do e-mail
def clean_subject(subject):
    # Remover caracteres especiais e números
    clean_subject = re.sub(r'[^A-Za-z\s]+', '', subject)

    # Remover múltiplos espaços
    clean_subject = re.sub(r'\s+', ' ', clean_subject).strip()

    return clean_subject


def create_labels(service, user_id='me'):
    label_names = {
        "important": "Emails Importantes",
        "not_important": "Emails Não Importantes",
        "Resumos": "Resumos diários",
        "Pagamentos": "Pagamentos",
        "Eventos": "Eventos",
        "Reuniões": "Reuniões",
        "Contratos": "Contratos",
        "Codigos_de_acesso": "Códigos de acesso",
        "A_Responder": "A Responder",
        "unclassified": "Não classificados"
    }
    label_ids = {}
    
    # Recupera as labels existentes
    try:
        existing_labels = service.users().labels().list(userId=user_id).execute().get('labels', [])
        existing_labels_dict = {label['name']: label['id'] for label in existing_labels}
    except Exception as e:
        print(f"Um erro ocorreu ao recuperar as labels existentes: {e}")
        existing_labels_dict = {}
    
    for key, label_name in label_names.items():
        if label_name in existing_labels_dict:
            # Label já existe
            label_ids[key] = existing_labels_dict[label_name]
        else:
            # Label não existe, cria-a
            label_body = {
                'name': label_name,
                'labelListVisibility': 'labelShow',
                'messageListVisibility': 'show'
            }
            try:
                label = service.users().labels().create(userId=user_id, body=label_body).execute()
                label_ids[key] = label['id']
            except Exception as e:
                print(f"Um erro ocorreu ao criar a label '{label_name}': {e}")
    
    return label_ids


def get_last_email_timestamp():
    if os.path.exists('last_email_timestamp.txt'):
        with open('last_email_timestamp.txt', 'r') as file:
            return file.read().strip()
    return None


def save_last_email_timestamp(timestamp):
    with open('last_email_timestamp.txt', 'w') as file:
        file.write(str(timestamp))


def get_emails(service, user_email, user_id='me'):
    """Recupera os e-mails da caixa de entrada a partir do último timestamp salvo."""
    last_email_timestamp = get_last_email_timestamp()

    if last_email_timestamp:
        query = f'before:{last_email_timestamp}'
    else: 
        #tempo = time.localtime()
        #tempo = parsedate_to_datetime(f'{str(time.strftime("%a"))} {str(time.strftime("%b"))} {str(tempo.tm_mday)} 00:00:01 {str(tempo.tm_year)}')
        #tempo = parsedate_to_datetime(f'{str(time.strftime("%a"))} {str(time.strftime("%b"))} {str('01')} 00:00:01 {str('2024')}')
        #print(tempo)
        #tempo = int(tempo.timestamp())
        tempo = int(1724245619)
        #print(tempo)
        query = f'before:{tempo}'
    
    try:
        results = service.users().messages().list(userId=user_id, q=query, maxResults=500).execute()
        messages = results.get('messages', [])
    except Exception as e:
        print(f"Erro ao recuperar emails: {e}")
        messages = []
        
    emails = []

    for message in messages:
        try:
            msg = service.users().messages().get(userId=user_id, id=message['id']).execute()

            payload = msg['payload']
            headers = payload['headers']
            subject = ""
            sender = ""
            timestamp = None
            for header in headers:
                if header['name'] == 'Subject':
                    subject = header['value']
                if header['name'] == 'From':
                    sender = header['value']
                if header['name'] == 'Date':
                    email_date = parsedate_to_datetime(header['value'])
                    timestamp = int(email_date.timestamp())

            if user_email in sender:
                continue

            parts = payload.get('parts', [])
            body = ''
            if parts:
                for part in parts:
                    if part['mimeType'] == 'text/plain':
                        body = part['body']['data']
                        body = base64.urlsafe_b64decode(body).decode('utf-8')
            else:
                body = payload.get('body', {}).get('data', '')
                if body:
                    body = base64.urlsafe_b64decode(body).decode('utf-8')
            emails.append({'subject': subject, 'sender': sender, 'body': body, 'id': message['id'], 'timestamp': timestamp})
        except Exception as e:
            print(f"Erro ao processar o email ID {message['id']}: {e}")

    if emails:
        # Salva o timestamp do e-mail mais recente
        save_last_email_timestamp(emails[-1]['timestamp'])
        
        # Salva os e-mails em um arquivo
        with open('todos_os_emails_jan.txt', 'a', encoding='utf-8') as f:
            for email in emails:
                email['body'] = clean_email_body(email['body'])
                email['subject'] = clean_subject(email['subject'])
                f.write(json.dumps(email, ensure_ascii=False) + '\n')
    
    return emails


def classify_emails(emails, batch_size=10, delay=90):
    classified_emails = []
    
    # Definir as categorias disponíveis
    categorias = [
        "important",
        "not_important",
        "Resumos",
        "Pagamentos",
        "Eventos",
        "Reuniões",
        "Contratos",
        "Codigos_de_acesso",
        "A_Responder",
        "nao_classificados"
    ]
    
    for i in range(0, len(emails), batch_size):
        batch = emails[i:i + batch_size]
        
        for email in batch:
            email['body'] = clean_email_body(email['body'])
            email['subject'] = clean_subject(email['subject'])
            content = f"{email['sender']} {email['subject']} {email['body']} {email['timestamp']}"

            # Carregar o modelo
            model = genai.GenerativeModel('gemini-1.5-flash')

            # Atualizar o prompt para múltiplas categorias
            prompt = (
                    f"Você está analisando e-mails corporativos e precisa classificá-los em uma das seguintes categorias: 'importante', 'não importante', 'pagamentos', 'eventos', 'reuniões', 'contratos', 'códigos de acesso', 'a responder'. Considere os seguintes critérios para a classificação: \
                    1. **Remetente**: Avalie se o e-mail é de diretores, superiores, clientes importantes ou outros contatos relevantes.\
                    2. **Assunto**: Identifique termos como 'urgente', 'ação necessária', 'prazo', 'revisão', 'aprovação', que possam indicar a importância do conteúdo.\
                    3. **Palavras-chave no corpo do e-mail**: \
                    - **Importante**: 'urgente', 'prioridade', 'ação imediata', 'necessário', 'crítico', 'essencial', 'alta prioridade'.\
                    - **Não importante**: 'para sua informação', 'FYI', 'sem urgência', 'não prioritário', 'informativo'.\
                    - **Pagamentos**: 'fatura', 'pagamento', 'cobrança', 'transferência', 'boleto', 'vencimento', 'liquidação', 'débito'.\
                    - **Eventos**: 'evento', 'workshop', 'seminário', 'palestra', 'celebração', 'encontro', 'lançamento', 'cerimônia'.\
                    - **Reuniões**: 'reunião', 'call', 'videoconferência', 'encontro', 'agendamento', 'discussão', 'pauta', 'agenda'.\
                    - **Contratos**: 'contrato', 'acordo', 'termo', 'condições', 'parceria', 'assinado', 'renovação', 'cláusula'.\
                    - **Códigos de acesso**: 'senha', 'código', 'PIN', 'autenticação', 'login', 'acesso', 'segurança', 'credencial'.\
                    - **A responder**: 'resposta necessária', 'aguardo retorno', 'ação requerida', 'por favor, responda', 'feedback', 'confirmação'.\
                    4. **Data de envio**: Considere se o e-mail foi enviado recentemente ou se está próximo de um prazo crítico.\
                    5. **Tamanho da cadeia de e-mails**: Determine a relevância com base na quantidade de respostas e no histórico de conversas.\
                    6. **Anexos**: Verifique a presença de anexos e sua relevância para a classificação (ex: contratos, propostas).\
                    7. **Marcadores ou categorias pré-existentes**: Leve em conta os marcadores ou categorias já aplicados ao e-mail.\
                    8. **Contexto organizacional**: Entenda o contexto geral do e-mail dentro da organização, como projetos em andamento ou decisões recentes.\
                    Com base nesses critérios, classifique o e-mail a seguir: {content}. Responda apenas com a categoria apropriada."

            )

            # Gerar a resposta do modelo
            response = model.generate_content(prompt)
            
            response_dict = response.to_dict()
            try:
                response_text = response_dict['candidates'][0]['content']['parts'][0]['text'].strip().lower()
                if response_text == 'não importante':
                    email['label'] = 'not_important'

                elif response_text == 'reuniões':
                    email['label'] = 'Reuniões'

                elif response_text == 'códigos de acesso':
                    email['label'] = 'Codigos_de_acesso'

                elif response_text == 'contratos':
                    email['label'] = 'Contratos'
                    
                elif response_text == 'eventos':
                    email['label'] = 'Eventos'

                elif response_text == 'pagamentos':
                    email['label'] = 'Pagamentos'

                elif response_text == 'importante':
                    email['label'] = 'important'  

                elif response_text == 'a responder':
                    email['label'] = 'A_responder'

                elif response_text == 'resumos':
                    email['label'] = 'Resumos'

                else: email['label'] = 'nao_classificados'    

                classified_emails.append(email)
            except Exception as e:
                print(f"Erro: {e}")
                continue

        # Aguardar antes de processar o próximo lote
        if i + batch_size < len(emails):
            time.sleep(delay)
    
    return classified_emails


def move_emails_to_labels(service, emails, label_ids, user_id='me'):
    for email in emails:
        if email['label'] in label_ids:
            label_id = label_ids[email['label']]
            msg_id = email['id']
            try:
                service.users().messages().modify(
                    userId=user_id,
                    id=msg_id,
                    body={'addLabelIds': [label_id]}
                ).execute()
            except Exception as e:
                print(f"Erro ao aplicar a label '{email['label']}' no email ID {msg_id}: {e}")
        else:
            print(f"Label '{email['label']}' não encontrada.")


# def resume_emails(emails_file):
#     bodies = []

#     with open(emails_file, 'r') as file:
#         for line in file:
#             email = json.loads(line.strip())

#             if email.get('label') == 'important' or email.get('label') == 'Pagamentos' or email.get('label') == 'Eventos' or email.get('label') == 'Reuniões' \
#                 or email.get('label') == 'Contratos' or email.get('label') == 'Codigos_de_acesso' or email.get('label') == 'A_Responder':
#                 bodies.append({'body': email.get('body'), 'subject': email.get('subject'), 'sender': email.get('sender')})

#     model = genai.GenerativeModel('gemini-1.5-flash')

#     # Gerar a resposta do modelo
#     response = model.generate_content(f"Você está analisando emails corporativos e eu preciso que você resuma cada email importante a seguir como se fosse um jornal. \
#                                       Coloque o Assunto do email, quem enviou o email e abaixo o resumo que você fizer. Os emails são: {bodies}."
#     )

#     response_dict = response.to_dict()
#     response_text = response_dict['candidates'][0]['content']['parts'][0]['text']

#     return response_text


# def send_email(service, email_content, email_address, resume_label):
#     try:
#         message = EmailMessage()
#         message.set_content(f"{email_content}")

#         tempo = time.localtime()
#         tempo_final = f"{tempo.tm_mday}/{tempo.tm_mon}/{tempo.tm_year}"

#         message["To"] = str(email_address)
#         message["From"] = str(email_address)
#         message["Subject"] = f"Resumo diário - {tempo_final}"

#         # Mensagem codificada
#         encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

#         create_message = {"raw": encoded_message}
        
#         send_message = service.users().messages().send(userId="me", body=create_message).execute()
        
#         service.users().messages().modify(
#             userId="me",
#             id=send_message["id"],
#             body={'addLabelIds': [resume_label[0]]}
#         ).execute()

#     except HttpError as error:
#         print(f"Um erro ocorreu: {error}")
    

def main():
    execucao = 0
    while execucao <= 0:
            service = get_gmail_service()

            user_profile = service.users().getProfile(userId='me').execute()
            email_address = user_profile.get('emailAddress')
            print(email_address)

            resume_label = []

            # results = service.users().labels().list(userId='me').execute()
            # all_labels = results.get('labels', [])
            # for label in all_labels:
            #     if label['name'] == 'Resumos diários':
            #         resume_label.append(label['id'])

            # # Criar labels no Gmail
            # label_ids = create_labels(service)

            # # Obter emails
            # emails = get_emails(service, user_email=email_address)
            # if emails:
            #     emails.pop()

            # # Filtrar e classificar emails
            # classified_emails = classify_emails(emails)

            # current_datetime = datetime.now().strftime("%d-%m-%Y")
            # str_current_datetime = str(current_datetime)

            # if classified_emails:
            #     file_name = str_current_datetime + ".txt"
            #     with open(file_name, 'a', encoding='utf-8') as f:
            #         for email in classified_emails:
            #             f.write(json.dumps(email, ensure_ascii=False) + '\n')

            #     # Mover emails para as labels correspondentes
            #     move_emails_to_labels(service, classified_emails, label_ids)

            # QUEBRAR CÓDIGO AQUI (SOMENTE RODAR APÓS 24H)

            # # Trecho do código para resumir os emails do dia
            # if os.path.exists(str_current_datetime + ".txt"):
            #     final_emails = resume_emails(str_current_datetime + ".txt")
            #     send_email(service, final_emails, email_address, resume_label)

            print("Emails classificados!")
            execucao += 1

if __name__ == '__main__':
    main()
