import { useState, type ChangeEvent } from "react";
import ChatInputTools from "./ChatInputTools";
import { uploadFiles } from "../../../../api/file";
import { useNavigate } from "react-router-dom";
import { useAnswer } from "../../../../contexts/AnswerContext";

export default function ChatInput() {
    const navigation = useNavigate()

    const [file1, setFile1] = useState<File | null>(null);
    const [file2, setFile2] = useState<File | null>(null);

    const { setAnswerContent } = useAnswer()

    const handleFile1Change = (e: ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0] || null;
        setFile1(file);
    };

    const handleFile2Change = (e: ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0] || null;
        setFile2(file);
    };

    const handleClick = async () => {
        if (!file1 || !file2) return
        const result: any = await uploadFiles(file1, file2)

        setAnswerContent(result.report_markdown!)

        navigation("/history")
    }

    return (
        <div className="w-229.25 h-33 flex flex-col justify-between py-5 rounded-[35px] text-[#B6B5C3]">
            <ChatInputTools onClick={handleClick} handleFile1Change={handleFile1Change} handleFile2Change={handleFile2Change} />
        </div>
    )
}