import type { PropsWithChildren, SubmitEvent } from "react";
import FormButton from "./FormButton";
import { useModal } from "../../../../contexts/ModalContext";
import RegisterModal from "../RegisterModal";
import LoginModal from "../LoginModal";

interface FormInterface extends PropsWithChildren {
    formType: "login" | "signup",
    onSubmit: () => void
}

export default function Form({ onSubmit, formType, children }: FormInterface) {
    const { openModal } = useModal();

    const formTitle = formType === "login" ? "Login" : "Register"

    const formButtonText = formType === "login" ? "Login" : "sign up"

    const formText = formType === "login"
        ?
            <>
                <p>Don't have an account?</p>
                <button onClick={() => openModal(<RegisterModal />)} className="text-[#5463BC]">Sign up</button>
            </>
        :
            <>
                <p>Already have an account?</p>
                <button onClick={() => openModal(<LoginModal />)} className="text-[#5463BC]">Sign in</button>
            </>

    const handleSubmit = (e: SubmitEvent<HTMLFormElement>) => {
        e.preventDefault()
        onSubmit()
    }

    return (
        <form onSubmit={handleSubmit} className="font-family-sans flex flex-col gap-12.5 px-7.5 pt-27.5 pb-17.5">
            <div className="flex flex-col gap-12.5">
                <div className="flex flex-col gap-10">
                    <h2 className="text-[44px] font-bold text-white">{formTitle}</h2>
                    <div className="flex items-center gap-4.5">
                        {formText}
                    </div>
                </div>
                <div className="flex flex-col gap-6">
                    {children}
                </div>
            </div>
            <div className="flex justify-end">
                <FormButton>
                    {formButtonText}
                </FormButton>
            </div>
        </form>
    )
}