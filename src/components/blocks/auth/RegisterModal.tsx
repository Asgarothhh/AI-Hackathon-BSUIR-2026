import { useState } from "react";
import Form from "./form/Form";
import FormGroup from "./form/FormGroup";
import { register } from "../../../api/register";
import AuthModal from "./AuthModal";

export default function RegisterModal() {
    const [email, setEmail] = useState("+375")
    const [password, setPassword] = useState("")
    const [confirmPassword, setConfirmPassword] = useState("")

    return (
        <AuthModal>
            <Form formType="signup" onSubmit={async () => await register(email, password)}>
                <FormGroup type="text" value={email} id="email" onChange={(value) => setEmail(value)} />
                <FormGroup type="password" value={password} id="password" onChange={(value) => setPassword(value)} />
                <FormGroup type="password" value={confirmPassword} id="confirmPassword" onChange={(value) => setConfirmPassword(value)} />
            </Form>
        </AuthModal>
    )
}