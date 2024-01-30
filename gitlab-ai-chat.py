import requests
import json
import openai
from flask import Flask, request

# AI token
gitlab_server_url= 'https://jihulab.com'
gitlab_private_token = "xxxxxxxxx"
ai_username = 'cs_ops'
headers = {"Private-Token": gitlab_private_token}
# GPT
openai.api_key = "sk-xxxxxxxxxxxx"
openai.base_url = "https://api.chatanywhere.com.cn"

def extract_info(webhook_json):
    messages = [{"role": "system", "content": "你是一位资深编程专家，负责代码变更的审查工作。当用户在 GitLab MR 合并请求的 Notes中提及你的时候，你需要回答他们的问题。"},]
    data = json.loads(webhook_json)
    event_type = data["event_type"]
    project_id = merge_request_iid = discussion_id = ''
    role = ''
    if event_type == "note":
      project_id = data["project_id"]
      merge_request_iid = data["merge_request"]["iid"]
      discussion_id = data["object_attributes"]["discussion_id"]
      # 获取 discussion_id 下面所有 discussions
      discussions_api_url = f"{gitlab_server_url}/api/v4/projects/{project_id}/merge_requests/{merge_request_iid}/discussions"
      response = requests.get(discussions_api_url, headers=headers)
      if response.status_code == 200:
          discussions = response.json()
          for item in discussions:
              if item['id'] == discussion_id:
                  for note in item["notes"]:
                      author_username = note['author']['username']
                      discussion = note['body']
                      if author_username == ai_username:
                          role='assistant'
                      else:
                          role='user'
                      item = {"role": role, "content": discussion}
                      messages.append(item)
          return messages, project_id, merge_request_iid, discussion_id


def add_note_to_merge_request(project_id, merge_request_iid, discussion_id, answer):
    note_api_url = f"{gitlab_server_url}/api/v4/projects/{project_id}/merge_requests/{merge_request_iid}/discussions/{discussion_id}/notes"
    data = {
        "body": answer
    }
    response = requests.post(note_api_url, headers=headers, data=data)
    if response.status_code == 201:
        print("Note added successfully.")
    else:
        print(f"Failed to add note. Status code: {response.status_code}, Response: {response.text}")

def chat_with_gpt(messages):
    response = openai.chat.completions.create(
        model = "gpt-3.5-turbo",
        messages = messages
    )
    return response.choices[0].message.content.replace('\n\n', '\n')

app = Flask(__name__)
@app.route('/note', methods=['POST'])
def note():
    webhook_json = request.data
    messages, project_id, merge_request_iid, discussion_id = extract_info(webhook_json)
    print(f"\nall messages:\n{messages}")
    print(f"\nlatest message:\n {messages[-1]}")
    if messages and messages[-1]["role"] !='assistant' and '@cs_ops' in messages[-1]["content"] :   # 排除 AI 自己的回复、排除没有 @cs_ops 的回复
        answer = chat_with_gpt(messages)
        add_note_to_merge_request(project_id, merge_request_iid, discussion_id, answer)
        return f"AI回复如下: {messages}"
    else:
        return 'AI回复自动跳过.'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9998)

