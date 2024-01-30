# coding=utf-8
from flask import Flask, request, Response
import logging
import gitlab
import requests, json
from concurrent.futures import ThreadPoolExecutor


logging.basicConfig(filename='gitlab_code_review.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')
app = Flask(__name__)
executor = ThreadPoolExecutor()


class AICodeReview():

    def __init__(self,
                 gitlab_private_token,
                 project_id,
                 merge_request_id,
                 tracing_id,
                 gitlab_server_url='https://gltest.phecda.cicc.com.cn',
                 llm_host='http://10.110.30.55:7072/gitlab_code_review',
                 ):
        self.gl = gitlab.Gitlab(
            gitlab_server_url,
            private_token=gitlab_private_token,
            timeout=300,
            api_version='4'
        )

        app.logger.info(f'[{tracing_id}] 初始化GitLab连接成功')

        # project
        self.project_id = project_id
        self.project = self.gl.projects.get(project_id)
        app.logger.info(f'找到project: {project_id}')

        # mr
        self.merge_request_id = merge_request_id
        self.merge_request = self.project.mergerequests.get(merge_request_id)
        app.logger.info(f'找到mr: {merge_request_id}')

        # changes
        self.changes = self.merge_request.changes()
        # print('找到changes, {}'.format(self.changes))

        # llm
        self.llm_host = llm_host

        # comments
        self.review_notes = []

        # note
        self.note = ''

        # tracing
        self.tracing_id = tracing_id

    def ai_code_review(self):

        for idx, change in enumerate(self.changes['changes']):

            messages = [
                {"role": "system",
                 "content": "你是一位资深编程专家，负责代码变更的审查工作。需要给出审查建议。在建议的开始需明确对此代码变更给出「拒绝」或「接受」的决定，并且以格式「变更评分：实际的分数」给变更打分，分数区间为0~100分。然后，以精炼的语言、严厉的语气指出存在的问题。如果你觉得必要的情况下，可直接给出修改后的内容。建议中的语句可以使用emoji结尾。你的反馈内容必须使用严谨的markdown格式。"
                 },
                {"role": "user",
                 "content": f"请review这部分代码变更{change}",
                 },
            ]

            tracing_id = f'{self.tracing_id}-{idx}'

            app.logger.info(f'[{tracing_id}] 思考中...')
            app.logger.info(f'[{tracing_id}] {messages}')

            response = requests.post(self.llm_host, headers={'Content-Type': 'application/json'},
                                     json={'messages': messages})

            # print(response)
            new_path = change['new_path']
            app.logger.info(f'[{tracing_id}] 对 {new_path} review中...')

            response_content = json.loads(response.content.decode('utf-8'))['comment']

            review_note = f'_`{tracing_id}`_' + '\n\n'
            review_note += f'# `{new_path}`' + '\n\n'
            review_note += f'{"AI review 意见如下:"}' + '\n\n'
            review_note += response_content

            self.review_notes.append(review_note)

        self.comment()

    def comment(self, notice=None):
        if notice is None:
            review_note = '\n\n---\n\n'.join(self.review_notes)
            self.note = {'body': review_note}
            self.merge_request.notes.create(self.note)
            app.logger.info(f'[{self.tracing_id}] review内容, {self.note}')
            app.logger.info(f'[{self.tracing_id}] review完成')
        else:
            self.note = {'body': notice}
            self.merge_request.notes.create(self.note)
            app.logger.info(f'[{self.tracing_id}] {notice}')


# receiving gitlab merge request webhook events to handle mr payload
@app.route('/webhook/copilot', methods=['POST'])
def copilot():
    # record the webhook uuid
    whk_uuid = request.headers['X-Gitlab-Webhook-UUID']

    # handle json payload
    data = request.get_json()
    project_id = data['project']['id']
    merge_request_id = data['object_attributes']['iid']

    # generate tracing id
    tracing_id = str(project_id) + '-' + str(merge_request_id) + '-' + str(whk_uuid)

    app.logger.info(f'[{tracing_id}] {data}')

    # print(data['object_attributes']['action'], data['object_attributes']['state'])
    if 'action' not in data['object_attributes']:
        app.logger.info(f'[{tracing_id}] Skipped, Webhook Testing')
        return Response('Skipped, Webhook Testing', status=200)

    if data['object_attributes']['state'] != 'opened':
        app.logger.info(
            f'[{tracing_id}] Skipped, 只处理开放状态合并请求的更新和创建事件: 当前状态:{data["object_attributes"]["state"]}')
        return Response('Skipped, 只处理开放状态合并请求的更新和创建事件', status=200)

    # 判断是否是代码变更
    # 创建mr触发AI code review
    if data['object_attributes']['action'] == 'open' and (data['changes'] is None or data['changes'] == {}):
        pass
    # 关闭再开启mr也会触发AI code review
    elif data['object_attributes']['action'] == 'reopen':
        pass
    # 更新mr触发AI code review
    elif data['object_attributes']['action'] == 'update' and 'oldrev' in data['object_attributes']:
        pass
    else:
        app.logger.info(f'[{tracing_id}] Skipped, 不是一个有效的代码变更，可能是title, assignee, labels等元信息变更')
        return Response('Skipped, 不是一个有效的代码变更，可能是title, assignee, labels等元信息变更', status=200)

    acr = AICodeReview(gitlab_server_url="https://gltest.phecda.cicc.com.cn",
                       gitlab_private_token="<your access token>",
                       project_id=project_id,
                       merge_request_id=merge_request_id,
                       tracing_id=tracing_id,
                       llm_host="http://10.110.30.55:7072/gitlab_code_review",
                       )
    executor.submit(acr.ai_code_review)

    return Response(mimetype='application/json', status=200, response='对话进行中')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888)

