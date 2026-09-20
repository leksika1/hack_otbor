# Agent Rules

## Repository exploration

- Перед вызовом Read проверять, не было ли уже прочитано содержимое данного файла в текущей сессии, и при наличии кэша использовать его вместо повторного чтения.

## Tool usage

- Перед чтением файла через Read убедитесь, что он существует, например, выполнив ls или test -f, либо дождитесь завершения команды, которая его создаёт.
- Перед попыткой завершить процессы agy сначала выполнить pgrep -af 'agy' и, если список не пуст, запустить kill/pkill, проверив их exit code; при ненулевом коде вывести ошибку и не продолжать без анализа.

## Working with the user

- После каждого рендера открывайте полученный файл и проверяйте, что изображение не обрезано по верхнему левому углу и находится по центру кадра.

## Progress and pacing

- After launching a background task, periodically read its output file (e.g., /tmp/claude-1000/.../tasks/<task-id>.output) until it contains a completion status, then proceed.
