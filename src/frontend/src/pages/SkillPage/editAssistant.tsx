import { useMessageStore } from "@/components/bs-comp/chatComponent/messageStore";
import { useToast } from "@/components/bs-ui/toast/use-toast";
import { changeAssistantStatusApi, saveAssistanttApi } from "@/controllers/API/assistant";
import { captureAndAlertRequestErrorHoc } from "@/controllers/request";
import { useAssistantStore } from "@/store/assistantStore";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { useNavigate } from "react-router-dom";
import Header from "./components/editAssistant/Header";
import Prompt from "./components/editAssistant/Prompt";
import Setting from "./components/editAssistant/Setting";
import TestChat from "./components/editAssistant/TestChat";
import { useTranslation } from "react-i18next";
import ApiMainPage from "@/components/bs-comp/apiComponent";

export default function editAssistant() {
    const { t } = useTranslation()
    const { id: assisId } = useParams()
    const navigate = useNavigate()
    // assistant data
    const { assistantState, changed, loadAssistantState, saveAfter, destroy } = useAssistantStore()
    const { startNewRound, insetSystemMsg, insetBsMsg, destory, setShowGuideQuestion } = useMessageStore()

    useEffect(() => {
        loadAssistantState(assisId, 'v1').then((res) => {
            setShowGuideQuestion(true)
            setGuideQuestion(res.guide_question?.filter((item) => item) || [])
            res.guide_word && insetBsMsg(res.guide_word)
        })
    }, [])

    // 展示的引导词独立存储
    const [guideQuestion, setGuideQuestion] = useState([])
    const [openChat, setOpenChat] = useState(true)
    const handleStartChat = async (save) => {
        if (!handleCheck()) return
        destory()
        setOpenChat(false)
        save ? await handleSave(true) : await new Promise((resolve) => setTimeout(resolve, 0))
        saveAfter()
        startNewRound(t('build.configurationUpdated'))
        setGuideQuestion(assistantState.guide_question.filter((item) => item))
        assistantState.guide_word && insetBsMsg(assistantState.guide_word)
        setOpenChat(true)
    }

    const { message, toast } = useToast()
    // 保存助手详细信息
    const handleSave = async (showMessage = false) => {
        if (!handleCheck()) return
        await captureAndAlertRequestErrorHoc(saveAssistanttApi({
            ...assistantState,
            flow_list: assistantState.flow_list.map(item => item.id),
            tool_list: assistantState.tool_list.map(item => item.id),
            knowledge_list: assistantState.knowledge_list.map(item => item.id),
            guide_question: assistantState.guide_question.filter((item) => item)
        })).then(res => {
            if (!res) return
            showMessage && message({
                title: t('prompt'),
                variant: 'success',
                description: t('skills.saveSuccessful')
            })
        })
    }

    // 上线助手
    const handleOnline = async () => {
        if (!handleCheck()) return
        await handleSave()
        await captureAndAlertRequestErrorHoc(changeAssistantStatusApi(assistantState.id, 1)).then(res => {
            if (res === false) return
            message({
                title: t('prompt'),
                variant: 'success',
                description: t('skills.onlineSuccessful')
            })
        })
        setTimeout(() => {
            navigate('/build')
        }, 1200);
    }

    // 校验助手数据
    const handleCheck = () => {
        const errors = []
        if (
            assistantState.max_token === undefined ||
            !Number.isInteger(assistantState.max_token) ||
            assistantState.max_token < 0 ||
            assistantState.max_token > 100 * 10000
        ) {
            errors.push(t('skills.chatHistoryMaxToken'));
        }
        if (!assistantState.model_name) {
            errors.push('模型不能为空')
        }
        if (assistantState.guide_question.some(que => que.length > 50)) {
            errors.push(t('skills.guideQuestions50'))
        }
        if (assistantState.guide_word.length > 1000) {
            errors.push(t('skills.promptWords1000'))
        }

        if (errors.length) {
            message({
                title: t('prompt'),
                variant: 'error',
                description: errors
            })
            return false
        }
        return true
    }

    // 销毁
    useEffect(() => {
        return destroy
    }, [])

    const [showApiPage, setShowApiPage] = useState(false)

    return <div className="bg-background-main">
        <Header onSave={() => handleSave(true)} onLine={handleOnline} onTabChange={(t) => setShowApiPage(t === 'api')}></Header>
        <div className="h-[calc(100vh-70px)]">
            <div className={`flex h-full ${showApiPage ? 'hidden' : ''}`}>
                <div className="w-[60%]">
                    <div className="text-md font-medium leading-none p-4 shadow-sm">{t('build.assistantConfiguration')}</div>
                    <div className="flex h-[calc(100vh-120px)]">
                        <Prompt></Prompt>
                        <Setting></Setting>
                    </div>
                </div>
                <div className="w-[40%] h-full bg-[#fff] relative">
                    {openChat && <TestChat guideQuestion={guideQuestion} assisId={assisId} onClear={() => handleStartChat(false)}></TestChat>}
                    {/* 变更触发保存的蒙版按钮 */}
                    {changed && <div className="absolute w-full bottom-0 h-60" onClick={() => handleStartChat(true)}></div>}
                </div>
            </div>
            <div className={`h-full ${showApiPage ? '' : 'hidden'}`}>
                <ApiMainPage />
            </div>
        </div>
    </div>
};
