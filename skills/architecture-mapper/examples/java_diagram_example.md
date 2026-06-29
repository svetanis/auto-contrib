# Java Architecture Map Example

Below is the generated class diagram for the requested Java codebase:

```mermaid
classDiagram
  class UserController {
    +getUser()
    +createUser()
  }
  class UserService {
    +saveToDatabase()
    +validateUser()
  }
  class UserRepository {
    +findById()
    +save()
  }
  
  UserController --> UserService
  UserService --> UserRepository
```
