import { useState } from "react";
import { login } from "../../../api/login";
import Form from "./form/Form";
import FormGroup from "./form/FormGroup";
import AuthModal from "./AuthModal";

export default function LoginModal() {
    const [email, setEmail] = useState("+375")
    const [password, setPassword] = useState("")

    return (
        <AuthModal>
            <Form formType="login" onSubmit={async () => await login(email, password)}>
                <FormGroup type="text" value={email} id="email" prefix="+375" onChange={(value) => setEmail(value)} />
                <FormGroup type="password" value={password} id="password" onChange={(value) => setPassword(value)} />
            </Form>
        </AuthModal>
    )
}