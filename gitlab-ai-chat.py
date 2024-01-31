import requests
import json
import openai
from flask import Flask, request

# token

gitlab_server_url= 'https://jihulab.com'
gitlab_private_token = "xxxxxxxxxxx"
ai_username = 'cs_ops'
headers = {"Private-Token": gitlab_private_token}

# GPT
openai.api_key = "sk-xxxxxxxxxxxxxx"
openai.base_url = "https://api.chatanywhere.com.cn"

mr_code_review_prompt = "你是是一位资深编程专家，负责代码变更的审查工作。需要给出审查建议。在建议的开始需明确对此代码变更给出「拒绝」或「接受」的决定，并且以格式「变更评分：实际的分数」给变更打分，分数区间为0~100分。然后，以精炼的语言、严厉的语气指出存在的问题，并且给出修改后的代码以供参考。建议中的语句可以使用emoji结尾。你的反馈内容必须使用严谨的markdown格式。整体反馈内容必须包含以下三点：1. 对变更的决定和描述 2.存在的问题和建议 3.修改建议。特别注意，这三点的markdown段落之间需要空一行。"
mr_chat_prompt = "你是一位资深编程专家，负责代码变更的审查工作。当用户在 GitLab MR 合并请求的 Notes中提及你的时候，你需要回答他们的问题。"
issue_chat_prompt = "你是一位资深文档编写专家、Gitlab专家以及代码专家，当用户在 GitLab Issues的Notes中提及你的时候，你需要根据他们的问题，给他们一些专业的建议，建议中的语句可以使用emoji结尾。你的反馈内容必须使用严谨的markdown格式。"

def extract_info(webhook_json):
    data = json.loads(webhook_json)
    event_type = data["event_type"]
    noteable_type = data["object_attributes"]["noteable_type"]
    project_id = data["project"]["id"]
    merge_request_iid = discussion_id = role = ''

# MR
    if event_type == "merge_request":
      merge_request_iid = data["object_attributes"]["iid"]
      mr_changes_api_url = f"{gitlab_server_url}/api/v4/projects/{project_id}/merge_requests/{merge_request_iid}/changes"
      response = requests.get(mr_changes_api_url, headers=headers)
      if response.status_code == 200:
          changes_json = response.json()
          changes_list = changes_json["changes"]
          return changes_list, project_id, merge_request_iid
# Note - MR
    if event_type == "note" and noteable_type == "MergeRequest":
      merge_request_iid = data["merge_request"]["iid"]
      discussion_id = data["object_attributes"]["discussion_id"]
      discussions_api_url = f"{gitlab_server_url}/api/v4/projects/{project_id}/merge_requests/{merge_request_iid}/discussions"
      messages = [{"role": "system", "content": mr_chat_prompt}]
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
      
# Note - Issue
    if event_type == "note" and noteable_type == "Issue":
      issue_iid = data["issue"]["iid"]
      discussion_id = data["object_attributes"]["discussion_id"]
      discussions_api_url = f"{gitlab_server_url}/api/v4/projects/{project_id}/issues/{issue_iid}/discussions"
      messages = [{"role": "system", "content": issue_chat_prompt}]
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
          return messages, project_id, issue_iid, discussion_id

# 添加 审查意见
def add_review_to_merge_request(project_id, merge_request_iid, answer):
    note_api_url = f"{gitlab_server_url}/api/v4/projects/{project_id}/merge_requests/{merge_request_iid}/notes"
    data = {
        "body": answer
    }
    response = requests.post(note_api_url, headers=headers, data=data)
    if response.status_code == 200:
        print("Review added successfully.")
    else:
        print(f"Failed to add note. Status code: {response.status_code}, Response: {response.text}")

# 添加 note - MR 
def add_note_to_merge_request(project_id, merge_request_iid, discussion_id, answer):
    note_api_url = f"{gitlab_server_url}/api/v4/projects/{project_id}/merge_requests/{merge_request_iid}/discussions/{discussion_id}/notes"
    data = {
        "body": answer
    }
    response = requests.post(note_api_url, headers=headers, data=data)
    if response.status_code == 200:
        print("Note added successfully.")
    else:
        print(f"Failed to add note. Status code: {response.status_code}, Response: {response.text}")

# 添加 note - issue
def add_note_to_issue(project_id, issue_iid, discussion_id, answer):
    note_api_url = f"{gitlab_server_url}/api/v4/projects/{project_id}/issues/{issue_iid}/discussions/{discussion_id}/notes"
    data = {
        "body": answer
    }
    response = requests.post(note_api_url, headers=headers, data=data)
    if response.status_code == 200:
        print("Note added successfully.")
    else:
        print(f"Failed to add note. Status code: {response.status_code}, Response: {response.text}")

# 提交给 AI
def chat_with_gpt(messages):
    response = openai.chat.completions.create(
        model = "gpt-3.5-turbo",
        messages = messages
    )
    total_tokens = response.usage.total_tokens
    ai_answer = response.choices[0].message.content.replace('\n\n', '\n')
    return ai_answer, total_tokens

# 监听
app = Flask(__name__)
@app.route('/gitlab_ai_webhook', methods=['POST'])
def gitlab_ai_webhook():
    webhook_json = request.data
    data = json.loads(webhook_json)
    event_type = data["event_type"]
    noteable_type = data["object_attributes"]["noteable_type"]
    if event_type == "merge_request" :       # 代码审查
      merge_request_state = data['object_attributes']['state']
      if merge_request_state == 'opened':
        changes_list, project_id, merge_request_iid = extract_info(webhook_json)
        for change in changes_list:
          question = f"请审查这部分代码变更: {change}"
          new_path = change['new_path']
          messages = [
              {"role": "system", "content": mr_code_review_prompt},
              {"role": "user", "content": question}
              ]
          ai_answer, total_tokens = chat_with_gpt(messages)
          total_answer = f'# {new_path}' + '\n\n' + f'{"AI review 意见如下:" } ({total_tokens} tokens)' + '\n\n' + ai_answer
          add_review_to_merge_request(project_id, merge_request_iid, total_answer)
        return f"AI回复完成{len(changes_list)}个变更审查。"
      else:
        return f"MR关闭动作, AI无需回复。"
    elif event_type == "note" and noteable_type == "MergeRequest":            # MR Note
      messages, project_id, merge_request_iid, discussion_id = extract_info(webhook_json)
      print(f"\nall messages:\n{messages}")
      if messages and messages[-1]["role"] !='assistant' and f'@{ai_username}' in messages[-1]["content"] :   # 排除 AI 自己的回复、排除没有 @{ai_username} 的回复
          ai_answer, total_tokens = chat_with_gpt(messages)
          add_note_to_merge_request(project_id, merge_request_iid, discussion_id, ai_answer)
          return f"AI回复如下: {ai_answer}"
      else:
          return 'AI回复自动跳过。'
    elif event_type == "note" and noteable_type == "Issue":            # Issue Note
      messages, project_id, issue_iid, discussion_id = extract_info(webhook_json)
      print(f"\nall messages:\n{messages}")
      if messages and messages[-1]["role"] !='assistant' and f'@{ai_username}' in messages[-1]["content"] :   # 排除 AI 自己的回复、排除没有 @{ai_username} 的回复
          ai_answer, total_tokens = chat_with_gpt(messages)
          add_note_to_issue(project_id, issue_iid, discussion_id, ai_answer)
          return f"AI回复如下: {ai_answer}"
      else:
          return 'AI回复自动跳过。'
    else:
        return '非指定类型的 Webhook,跳过。'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9999)

