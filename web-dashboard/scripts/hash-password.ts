import { hash } from "@node-rs/argon2";

async function readSecret() {
  if (!process.stdin.isTTY)
    throw new Error("auth:hash requires an interactive terminal");
  process.stdout.write("Password: ");
  process.stdin.setRawMode(true);
  process.stdin.setEncoding("utf8");
  process.stdin.resume();
  let password = "";
  for await (const chunk of process.stdin) {
    const key = String(chunk);
    if (key === "\u0003") process.exit(130);
    if (key === "\r" || key === "\n") break;
    if (key === "\u007f") password = password.slice(0, -1);
    else password += key;
  }
  process.stdin.setRawMode(false);
  process.stdin.pause();
  process.stdout.write("\n");
  if (!password) throw new Error("Password cannot be empty");
  return password;
}

const password = await readSecret();
console.log(
  await hash(password, {
    algorithm: 2,
    memoryCost: 19456,
    timeCost: 2,
    parallelism: 1,
    outputLen: 32,
  }),
);
