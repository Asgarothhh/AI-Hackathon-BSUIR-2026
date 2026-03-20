import type { PropsWithChildren } from "react";

export default function Container({ children }: PropsWithChildren) {
    return (
        <div>
            {children}
        </div>
    )
}