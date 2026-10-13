# Stack: Flutter

id: stack/flutter
version: 1.0.0

## Rules

- This is a Flutter/Dart project, not React or Next.js.
- Preserve existing state-management and routing patterns.
- Do not manually edit generated files such as `*.g.dart`, `*.freezed.dart`, or dependency-injection generated output.
- Regenerate generated files using the repository's build-runner workflow.
- Do not invent packages, platform channels, routes, services or environment variables.
- Be careful with Android/iOS permissions, signing config and generated native files.

## Checks

Preferred checks:

```bash
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter analyze
flutter test
```

Use only commands that fit the project.

## Conflicts

- Conflicts with Next.js stack rules.
- Conflicts with Hono backend rules.
