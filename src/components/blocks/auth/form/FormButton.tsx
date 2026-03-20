import type { PropsWithChildren } from "react";

export default function FormButton({ children }: PropsWithChildren) {
    return (
        <button type="submit" className="w-fit flex gap-2 items-center py-3 px-5.5 bg-[#FFFFFF99] transition border border-[#FFFFFF99] rounded-[25px]">
            {children}

            <img src="/icon/auth/login.svg" alt="" />
        </button>
    )
}