import type { PropsWithChildren } from "react";

export default function AuthModal({ children }: PropsWithChildren) {
    return (
        <div style={{
            background: "linear-gradient(150.57deg, #DFE1EC 3.56%, #6D79BE 70.16%, #505EB3 96.93%)"
        }} className="rounded-xl w-112.5">
            {children}
        </div>
    )
}