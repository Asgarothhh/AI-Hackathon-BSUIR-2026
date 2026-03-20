import { createContext, useContext, useState, type Dispatch, type PropsWithChildren } from "react";

interface AnswerContextInterface {
    answerContent: string
    setAnswerContent: Dispatch<React.SetStateAction<string>>
}

const AnswerContext = createContext({} as AnswerContextInterface);

export function useAnswer() {
    return useContext(AnswerContext);
}

export function AnswerProvider({ children }: PropsWithChildren) {
    const [answerContent, setAnswerContent] = useState("");

    return (
        <AnswerContext.Provider value={{ answerContent, setAnswerContent }}>
            {children}
        </AnswerContext.Provider>
    );
}

