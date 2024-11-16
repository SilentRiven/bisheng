from bisheng.api.services.assistant_agent import AssistantAgent
from bisheng.api.services.llm import LLMService
from bisheng.database.models.knowledge import KnowledgeDao
from bisheng.workflow.callback.event import OutputMsgData
from bisheng.workflow.nodes.base import BaseNode
from bisheng.workflow.nodes.prompt_template import PromptTemplateParser
from bisheng_langchain.gpts.assistant import ConfigurableAssistant

agent_executor_dict = {
    'ReAct': 'get_react_agent_executor',
    'function call': 'get_openai_functions_agent_executor',
}


class AgentNode(BaseNode):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 判断是单次还是批量
        self._tab = self.node_data.tab['value']

        # 解析prompt
        self._system_prompt = PromptTemplateParser(template=self.node_params['system_prompt'])
        self._system_variables = self._system_prompt.extract()
        self._user_prompt = PromptTemplateParser(template=self.node_params['user_prompt'])
        self._user_variables = self._user_prompt.extract()

        # 聊天消息
        self._chat_history_flag = self.node_params['chat_history_flag']['flag']
        self._chat_history_num = self.node_params['chat_history_flag']['number']

        self._llm = LLMService.get_bisheng_llm(model_id=self.node_params['model_id'],
                                               temperature=self.node_params.get(
                                                   'temperature', 0.3))

        # 是否输出结果给用户
        self._output_user = self.node_params.get('output_user', False)

        # tools
        self._tools = self.node_params['tool_list']

        # knowledge
        self._knowledge_ids = self.node_params['knowledge_id']

        # agent
        self._agent_executor_type = 'get_react_agent_executor'
        self._agent = None

    def _init_agent(self, system_prompt: str):
        # 获取配置的助手模型列表
        assistant_llm = LLMService.get_assistant_llm()
        if not assistant_llm.llm_list:
            raise Exception('助手推理模型列表为空')
        default_llm = [
            one for one in assistant_llm.llm_list if one.model_id == self.node_params['model_id']
        ][0]
        self._agent_executor_type = default_llm.agent_executor_type
        knowledge_retriever = {
            'max_content': default_llm.knowledge_max_content,
            'sort_by_source_and_index': default_llm.knowledge_sort_index
        }

        func_tools = self._init_tools()
        knowledge_tools = self._init_knowledge_tools(knowledge_retriever)
        tools = func_tools.extend(knowledge_tools)
        self._agent = ConfigurableAssistant(
            agent_executor_type=agent_executor_dict.get(self._agent_executor_type),
            tools=tools,
            llm=self._llm,
            assistant_message=system_prompt,
        )

    def _init_tools(self):
        if self._tools:
            tool_ids = [int(one['key']) for one in self._tools]
            return AssistantAgent.init_tools_by_toolid(tool_ids, self._llm, None)
        else:
            return []

    def _init_knowledge_tools(self, knowledge_retriever: dict):
        if not self._knowledge_ids:
            return []
        knowledge_list = KnowledgeDao.get_list_by_ids(self._knowledge_ids)
        tools = []
        for one in knowledge_list:
            tool = AssistantAgent.sync_init_knowledge_tool(
                one,
                self._llm,
                None,
                knowledge_retriever=knowledge_retriever,
            )
            tools += tool
        return tools

    def _run(self, unique_id: str):
        ret = {}
        variable_map = {}
        for one in self._system_variables:
            variable_map[one] = self.graph_state.get_variable_by_str(one)
        system_prompt = self._system_prompt.format(variable_map)
        self._init_agent(system_prompt)

        if self._tab == 'single':
            ret['output'] = self._run_once(None, unique_id, 'output')
        else:
            for index, one in enumerate(self.node_params['batch_variable']):
                output_key = self.node_params['output'][index]['key']
                ret[output_key] = self._run_once(one, unique_id, output_key)

        if self._output_user:
            # 非stream 模式，处理结果
            for k, v in ret.items():
                self.callback_manager.on_output_msg(
                    OutputMsgData(
                        node_id=self.id,
                        msg=v,
                        unique_id=unique_id,
                        output_key=k,
                    ))
        return ret

    def _run_once(self, input_variable: str = None, unique_id: str = None, output_key: str = None):
        """
        input_variable: 输入变量，如果是batch，则需要传入一个list，否则为None
        """
        # 说明是引用了批处理的变量, 需要把变量的值替换为用户选择的变量
        special_variable = f'{self.id}.batch_variable'
        variable_map = {}
        for one in self._system_variables:
            if input_variable and one == special_variable:
                variable_map[one] = self.graph_state.get_variable_by_str(input_variable)
                continue
            variable_map[one] = self.graph_state.get_variable_by_str(one)
        # system = self._system_prompt.format(variable_map)

        variable_map = {}
        for one in self._user_variables:
            if input_variable and one == special_variable:
                variable_map[one] = self.graph_state.get_variable_by_str(input_variable)
                continue
            variable_map[one] = self.graph_state.get_variable_by_str(one)
        user = self._user_prompt.format(variable_map)

        chat_history = None
        if self._chat_history_flag:
            chat_history = self.graph_state.get_history_memory()[-self._chat_history_num:]

        if self._agent_executor_type == 'get_react_agent_executor':
            result = self._agent.invoke({'input': user, 'chat_history': chat_history})
        else:
            result = self._agent.invoke(user)

        return result
